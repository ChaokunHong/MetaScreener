from flask import render_template, request, redirect, url_for, flash, jsonify, current_app, send_from_directory
from . import quality_bp # Import the blueprint
from werkzeug.utils import secure_filename # For securing filenames
import os
import json # Import Python's json library

# We will also need to import services and forms later
from .services import process_uploaded_document, get_assessment_result, QUALITY_ASSESSMENT_TOOLS, _assessments_db, QA_PDF_UPLOAD_DIR
# from .forms import DocumentUploadForm, AssessmentReviewForm 

# Allowed extensions for PDF files
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@quality_bp.route('/upload', methods=['GET', 'POST'])
def upload_document_for_assessment():
    if request.method == 'POST':
        if 'pdf_file' not in request.files:
            flash('No PDF file part in the request.', 'error')
            return redirect(request.url)
        
        file = request.files['pdf_file']
        
        if file.filename == '':
            flash('No PDF file selected.', 'error')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            
            # Get the selected document type from the form
            selected_document_type = request.form.get('document_type')
            # If the value from select is "" (e.g. for "Let AI Decide / Not Specified")
            # it will be passed as an empty string to process_uploaded_document,
            # which then correctly sets it to "Unknown" if appropriate.

            # The service function expects a file stream
            assessment_id = process_uploaded_document(file.stream, original_filename, selected_document_type)
            
            # Check the actual status from the service layer after processing
            current_assessment_status = _assessments_db.get(assessment_id, {}).get('status')
            current_assessment_message = _assessments_db.get(assessment_id, {}).get('message', "Unknown error")

            if assessment_id and current_assessment_status != 'error':
                flash(f'Document \'{original_filename}\' uploaded. Assessment process initiated.', 'success')
                return redirect(url_for('.view_assessment_result', assessment_id=assessment_id))
            else:
                flash(f'Error initiating assessment for \'{original_filename}\'. Reason: {current_assessment_message}', 'error')
                return redirect(request.url)
        else:
            flash('Invalid file type. Only PDF files are allowed.', 'error')
            return redirect(request.url)
            
    # For GET request, pass the QUALITY_ASSESSMENT_TOOLS to the template
    return render_template('quality_assessment_upload.html', assessment_tools_info=QUALITY_ASSESSMENT_TOOLS)

@quality_bp.route('/result/<assessment_id>')
def view_assessment_result(assessment_id):
    result_data = get_assessment_result(assessment_id)
    if not result_data:
        flash('Assessment result not found.', 'error')
        return redirect(url_for('.upload_document_for_assessment'))

    result_data_json_str = "{}" # Default to empty JSON object string
    try:
        # For initial data for JS, be very selective to avoid JSON parsing issues.
        # The polling mechanism will fetch more complete/raw data from the API.
        # Jinja server-side rendering will use the full 'result_data' object.
        selective_initial_data = {
            "status": result_data.get("status"),
            "filename": result_data.get("filename"),
            "document_type": result_data.get("document_type"),
            "progress": result_data.get("progress"),
            # DO NOT include assessment_details or raw_text here for JS init.
        }
        result_data_json_str = json.dumps(selective_initial_data)
    except Exception as e:
        current_app.logger.error(f"Error preparing result_data_json_str for JS for assessment {assessment_id}: {e}")
        # result_data_json_str remains "{}"

    current_app.logger.info(f"VIEW_RESULT_ROUTE: For assessment_id {assessment_id}, result_data being passed to template:")
    current_app.logger.info(f"VIEW_RESULT_ROUTE: result_data.status = {result_data.get('status')}")
    current_app.logger.info(f"VIEW_RESULT_ROUTE: result_data.assessment_details type = {type(result_data.get('assessment_details'))}")
    current_app.logger.info(f"VIEW_RESULT_ROUTE: result_data.assessment_details content = {result_data.get('assessment_details')}")

    return render_template(
        'quality_assessment_result.html', 
        result=result_data, # Full data for Jinja server-side rendering
        result_json_for_js=result_data_json_str, # Sanitized, minimal JSON string for JS
        assessment_id=assessment_id,
        QUALITY_ASSESSMENT_TOOLS=QUALITY_ASSESSMENT_TOOLS
    )

# --- NEW API ENDPOINT FOR ASSESSMENT STATUS --- #
@quality_bp.route('/assessment_status/<assessment_id>')
def assessment_status(assessment_id):
    assessment_data = get_assessment_result(assessment_id)
    if assessment_data:
        response_data = {
            "status": assessment_data.get("status"),
            "progress": assessment_data.get("progress"),
            "filename": assessment_data.get("filename"),
            "document_type": assessment_data.get("document_type")
        }
        if assessment_data.get("status") == "completed":
            # Optionally, if needed by JS immediately on completion before reload (currently not used this way)
            # response_data["assessment_details_count"] = len(assessment_data.get("assessment_details", [])) if isinstance(assessment_data.get("assessment_details"), list) else 0
            pass # Reload handles showing details
        elif assessment_data.get("status") == "error":
             response_data["message"] = assessment_data.get("message", "An unknown error occurred.")

        return jsonify(response_data)
    return jsonify({"status": "error", "message": "Assessment not found"}), 404
# --- END NEW API ENDPOINT --- #

# --- Debug endpoint for assessment data --- #
@quality_bp.route('/debug_assessment/<assessment_id>')
def debug_assessment_data(assessment_id):
    assessment_data = get_assessment_result(assessment_id)
    if assessment_data:
        details = assessment_data.get('assessment_details')
        details_count = len(details) if isinstance(details, list) else 0
        first_result_summary = {}
        if details and isinstance(details, list) and details_count > 0:
            first_item = details[0]
            if isinstance(first_item, dict):
                first_result_summary = {
                    "criterion_id": first_item.get("criterion_id"),
                    "judgment": first_item.get("judgment")
                }

        debug_data = {
            "status": assessment_data.get("status"),
            "document_type": assessment_data.get("document_type"),
            "has_assessment_details": bool(details),
            "assessment_details_count": details_count,
            "first_result_summary": first_result_summary, 
            "progress": assessment_data.get("progress")
        }
        return jsonify(debug_data)
    return jsonify({"error": "Assessment not found"}), 404

# --- HTML debug view for assessment details ---
@quality_bp.route('/view_details/<assessment_id>')
def view_details(assessment_id):
    """Simple HTML view for assessment details without full template complexity"""
    result_data = get_assessment_result(assessment_id)
    if not result_data:
        return f"<h1>Assessment {assessment_id} not found</h1>"
    
    html_output = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Assessment Details #{assessment_id}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .header {{ background-color: #4CAF50; color: white; padding: 15px; }}
            .container {{ margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Assessment Details: {result_data.get('filename', 'Unknown')}</h1>
            <p>Status: {result_data.get('status', 'Unknown')} | Type: {result_data.get('document_type', 'Unknown')}</p>
        </div>
        <div class="container">
    """
    
    assessment_details_list = result_data.get('assessment_details')
    if isinstance(assessment_details_list, list) and assessment_details_list:
        html_output += f"""
            <h2>Assessment Results ({len(assessment_details_list)} items)</h2>
            <table>
                <tr>
                    <th>Criterion</th>
                    <th>Judgment</th>
                    <th>Reason</th>
                </tr>
        """
        
        for item in assessment_details_list:
            html_output += f"""
                <tr>
                    <td>{item.get('criterion_text', 'No text')}</td>
                    <td>{item.get('judgment', 'No judgment')}</td>
                    <td>{item.get('reason', 'No reason')}</td>
                </tr>
            """
        
        html_output += "</table>"
    else:
        html_output += """
            <div style="color: red; padding: 20px; background-color: #ffeeee; border: 1px solid #ffcccc;">
                <h2>No assessment details found</h2>
                <p>This assessment does not contain any evaluation details.</p>
                <p>Details type: {type(assessment_details_list).__name__}, Details content: {assessment_details_list}</p>
            </div>
        """
    
    html_output += "</div></body></html>"
    
    return html_output

# --- NEW ROUTE TO SERVE SAVED PDFs FOR PREVIEW --- #
@quality_bp.route('/serve_pdf/<assessment_id>')
def serve_saved_pdf(assessment_id):
    assessment_data = get_assessment_result(assessment_id)
    if not assessment_data:
        return "Assessment data not found", 404
    
    saved_filename = assessment_data.get('saved_pdf_filename')
    if not saved_filename:
        # This case can happen if PDF saving failed during upload, or for older assessments
        # before this feature was added.
        # You could serve a placeholder PDF or an error message.
        # For now, let's return a 404 and the JS client can handle it.
        current_app.logger.warning(f"No saved_pdf_filename found for assessment_id {assessment_id}. Cannot serve PDF.")
        return "PDF record not found for this assessment or PDF was not saved.", 404

    # QA_PDF_UPLOAD_DIR is imported from services.py
    # Ensure the directory path is absolute for send_from_directory if it's not already
    # However, QA_PDF_UPLOAD_DIR should be absolute as defined in services.py
    current_app.logger.info(f"Attempting to serve PDF: {saved_filename} from directory: {QA_PDF_UPLOAD_DIR} for assessment {assessment_id}")
    try:
        return send_from_directory(QA_PDF_UPLOAD_DIR, saved_filename, as_attachment=False)
    except FileNotFoundError:
        current_app.logger.error(f"File not found: {saved_filename} in directory {QA_PDF_UPLOAD_DIR}")
        return "PDF file not found on server.", 404
    except Exception as e:
        current_app.logger.error(f"Error serving PDF {saved_filename} for assessment {assessment_id}: {e}")
        return "Error serving PDF.", 500

# We need to access _assessments_db for the flash message, either pass it or check status differently
# For simplicity, let's import it here. In a real app, this would be a proper database call.

# We will need more routes:
# - Route for batch upload status / results table
# - API endpoint for AI to classify document type (if we go that route)
# - API endpoint for AI to assess based on criteria
# - Route for user to submit their own review/override AI 