from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import csv
from datetime import datetime
import os

# Application setup
application = Flask(__name__)
CORS(application)

# Configuration constants
EXCEL_DIRECTORY = 'all excels/'
APPLICATIONS_CSV_FILENAME = 'all_applied_applications_history.csv'
APPLICATIONS_FILE_PATH = os.path.join(EXCEL_DIRECTORY, APPLICATIONS_CSV_FILENAME)


@application.route('/')
def serve_homepage():
    """Render the main index page."""
    return render_template('index.html')


@application.route('/applied-jobs', methods=['GET'])
def retrieve_applied_jobs():
    """Fetch all applied job records from the CSV file."""
    try:
        job_records = []
        with open(APPLICATIONS_FILE_PATH, 'r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for record in csv_reader:
                job_records.append({
                    'Job_ID': record['Job ID'],
                    'Title': record['Title'],
                    'Company': record['Company'],
                    'HR_Name': record['HR Name'],
                    'HR_Link': record['HR Link'],
                    'Job_Link': record['Job Link'],
                    'External_Job_link': record['External Job link'],
                    'Date_Applied': record['Date Applied']
                })
        return jsonify(job_records)

    except FileNotFoundError:
        return jsonify({"error": "No applications history found"}), 404
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@application.route('/applied-jobs/<job_id>', methods=['PUT'])
def refresh_application_timestamp(job_id):
    """Update the Date Applied field for a specific job ID."""
    try:
        updated_rows = []
        
        if not os.path.exists(APPLICATIONS_FILE_PATH):
            return jsonify({"error": f"CSV file not found at {APPLICATIONS_FILE_PATH}"}), 404

        # Read existing data
        with open(APPLICATIONS_FILE_PATH, 'r', encoding='utf-8') as input_file:
            csv_reader = csv.DictReader(input_file)
            field_headers = csv_reader.fieldnames
            job_exists = False

            for row_data in csv_reader:
                if row_data['Job ID'] == job_id:
                    row_data['Date Applied'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    job_exists = True
                updated_rows.append(row_data)

        if not job_exists:
            return jsonify({"error": f"Job ID {job_id} not found"}), 404

        # Write updated data back
        with open(APPLICATIONS_FILE_PATH, 'w', encoding='utf-8', newline='') as output_file:
            csv_writer = csv.DictWriter(output_file, fieldnames=field_headers)
            csv_writer.writeheader()
            csv_writer.writerows(updated_rows)

        return jsonify({"message": "Date Applied updated successfully"}), 200

    except Exception as error:
        print(f"Error updating applied date: {str(error)}")
        return jsonify({"error": str(error)}), 500


if __name__ == '__main__':
    application.run(debug=True)
