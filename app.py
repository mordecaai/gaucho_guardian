from flask import Flask, render_template, jsonify, request
from course_service import (
    search_courses, get_course_info, get_section_details, 
    get_departments, filter_courses_by_schedule
)
import os
import json

app = Flask(__name__)

# Check for API key
if not os.environ.get('UCSB_API_KEY'):
    print("WARNING: UCSB_API_KEY environment variable not set. API calls will fail.")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/departments")
def api_departments():
    """Get list of all departments"""
    return jsonify(get_departments())


@app.route("/api/search", methods=["GET", "POST"])
def api_search():
    """Search for courses"""
    if request.method == "POST":
        data = request.get_json()
        query = data.get("q", "").strip() if data else ""
        department = data.get("dept", "").strip() if data else ""
        selected_courses = data.get("selectedCourses", []) if data else []
    else:
        query = request.args.get("q", "").strip()
        department = request.args.get("dept", "").strip()
        selected_courses = []
    
    try:
        results = search_courses(query=query, department=department)
        
        # Filter by schedule if selected courses provided
        if selected_courses:
            results = filter_courses_by_schedule(results, selected_courses)
        
        return jsonify({"success": True, "courses": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/course/<path:course_id>")
def api_course(course_id):
    """Get detailed course information by courseId"""
    try:
        # Flask automatically URL-decodes the path parameter
        course_data = get_course_info(course_id)
        if course_data:
            return jsonify({"success": True, "course": course_data})
        else:
            return jsonify({"success": False, "error": f"Course not found: {course_id}"}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/section", methods=["POST"])
def api_section():
    """Get section details for a specific lecture + section combination"""
    try:
        data = request.get_json()
        lecture_code = data.get("lectureCode", "")
        section_code = data.get("sectionCode", "")
        
        section_data = get_section_details(lecture_code, section_code)
        if section_data:
            return jsonify({"success": True, "course": section_data})
        else:
            return jsonify({"success": False, "error": "Section not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
