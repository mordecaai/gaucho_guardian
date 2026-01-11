from flask import Flask, render_template, jsonify, request
from course_service import (
    search_courses, get_course_info, get_section_details, 
    get_departments, filter_courses_by_schedule
)
from schedule_optimizer import optimize_schedules, format_schedule_result
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
        # When filtering by schedule, use a lower limit to avoid performance issues
        # Filtering requires loading full course data for each course, which is expensive
        if selected_courses:
            # Reduce limit significantly when filtering to avoid lag
            if not query:
                limit = 200 if not department else 150  # Much lower when filtering all departments
            else:
                limit = 100  # Standard limit when searching with a query
        else:
            # Use higher limit when browsing without filtering
            if not query:
                limit = 1000 if not department else 500  # Show more when browsing all departments
            else:
                limit = 100  # Standard limit when searching with a query
        
        results = search_courses(query=query, department=department, limit=limit)
        
        # Filter by schedule if selected courses provided
        if selected_courses:
            try:
                # Limit processing to avoid extreme lag - only process first 300 courses max
                max_filter_process = 300
                results_to_filter = results[:max_filter_process]
                filtered_results = filter_courses_by_schedule(results_to_filter, selected_courses)
                # Limit filtered results to reasonable number
                results = filtered_results[:200]
            except Exception as e:
                import traceback
                traceback.print_exc()
                # If filtering fails, return courses without filtering rather than failing completely
                print(f"Warning: Schedule filtering failed: {e}")
                results = results  # Continue with unfiltered results
        
        return jsonify({"success": True, "courses": results})
    except Exception as e:
        import traceback
        traceback.print_exc()
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


@app.route("/api/optimize-schedule", methods=["POST"])
def api_optimize_schedule():
    """Find optimal schedule combinations for selected courses"""
    try:
        data = request.get_json()
        course_ids = data.get("courseIds", [])
        preferences = data.get("preferences", {})
        max_results = data.get("maxResults", 10)
        
        if not course_ids:
            return jsonify({"success": False, "error": "No courses provided"}), 400
        
        # Optimize schedules
        scored_schedules = optimize_schedules(course_ids, preferences, max_results)
        
        # Format results
        results = []
        for scored_schedule in scored_schedules:
            formatted = format_schedule_result(scored_schedule, course_ids)
            results.append(formatted)
        
        return jsonify({"success": True, "schedules": results})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
