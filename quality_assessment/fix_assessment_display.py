"""
Manual fix script for assessment data display issues

Run this script if you see an assessment with 'completed' status but no visible results.
This will ensure the assessment_details field is properly populated and saved.

Usage: python -m quality_assessment.fix_assessment_display [assessment_id]
If no assessment_id is provided, it will check all assessments.
"""

import sys
from quality_assessment.services import _assessments_db, _save_assessments_to_file

def fix_assessment_display(assessment_id=None):
    """Fix display issues with assessments"""
    if assessment_id:
        # Fix specific assessment
        if assessment_id in _assessments_db:
            assessment = _assessments_db[assessment_id]
            print(f"Examining assessment {assessment_id}...")
            _fix_single_assessment(assessment_id, assessment)
        else:
            print(f"Assessment {assessment_id} not found in database.")
    else:
        # Check all assessments
        print(f"Checking all {len(_assessments_db)} assessments...")
        for aid, assessment in _assessments_db.items():
            _fix_single_assessment(aid, assessment)
    
    # Save changes
    _save_assessments_to_file()
    print("Done. Changes saved.")

def _fix_single_assessment(assessment_id, assessment):
    """Fix a single assessment if needed"""
    # Check if assessment is marked completed but has no details
    if assessment.get('status') == 'completed' and not assessment.get('assessment_details'):
        print(f"  Assessment {assessment_id} is completed but has no details! Checking...")
        
        # If progress indicates completion but details are missing, this is a display issue
        if assessment.get('progress', {}).get('message') == 'Assessment completed!':
            print(f"  Creating placeholder assessment details for {assessment_id}")
            # Create minimal placeholder assessment details
            assessment['assessment_details'] = [{
                "criterion_id": "placeholder",
                "criterion_text": "This is a placeholder criterion. The assessment was marked complete but had missing details.",
                "judgment": "Error: Details Missing",
                "reason": "The assessment process completed but did not properly store assessment details.",
                "evidence_quotes": ["No evidence quotes available"]
            }]
            print(f"  Assessment {assessment_id} fixed with placeholder content.")
    
    # If assessment has details, verify they are properly structured
    elif assessment.get('assessment_details'):
        details_count = len(assessment.get('assessment_details', []))
        print(f"  Assessment {assessment_id} has {details_count} detail items.")
        # Check if the first item has all required fields
        if details_count > 0:
            first_item = assessment['assessment_details'][0]
            missing_fields = []
            for required_field in ['criterion_id', 'criterion_text', 'judgment', 'reason']:
                if required_field not in first_item:
                    missing_fields.append(required_field)
            
            if missing_fields:
                print(f"  Warning: Assessment {assessment_id} is missing fields: {', '.join(missing_fields)}")

if __name__ == "__main__":
    # Get assessment_id from command line if provided
    assessment_id = sys.argv[1] if len(sys.argv) > 1 else None
    fix_assessment_display(assessment_id) 