"""
Debug script to inspect quality assessment data
Run with: python -m quality_assessment.debug_data
"""

from quality_assessment.services import _assessments_db
import json

def inspect_assessment_data():
    """Print information about all assessment data"""
    print(f"Total assessments in storage: {len(_assessments_db)}")
    
    for assessment_id, data in _assessments_db.items():
        print(f"\n{'='*50}")
        print(f"Assessment ID: {assessment_id}")
        print(f"Status: {data.get('status', 'Missing status')}")
        print(f"Document Type: {data.get('document_type', 'Missing type')}")
        
        if 'assessment_details' in data and data['assessment_details']:
            details = data['assessment_details']
            print(f"Assessment details: {len(details)} items")
            
            # Print the first assessment detail as example
            if details:
                print("\nFirst assessment item:")
                example = details[0]
                print(f"  Criterion ID: {example.get('criterion_id', 'Missing')}")
                print(f"  Judgment: {example.get('judgment', 'Missing')}")
                print(f"  Has reason: {'Yes' if example.get('reason') else 'No'}")
                print(f"  Evidence quotes: {len(example.get('evidence_quotes', []))}")
        else:
            print("No assessment details found!")
            
        if 'error' in data or 'message' in data:
            print(f"Error/Message: {data.get('error', data.get('message', 'N/A'))}")
            
        # Print nested progress information
        if 'progress' in data:
            progress = data['progress']
            print(f"Progress: current={progress.get('current', 'N/A')}, total={progress.get('total', 'N/A')}")
            print(f"Progress message: {progress.get('message', 'N/A')}")

if __name__ == "__main__":
    inspect_assessment_data()
    print("\nDone.") 