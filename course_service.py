"""
Course Service - Handles fetching and caching course data from UCSB API
"""
import json
import requests
from pathlib import Path
from typing import Optional, Dict, List
from config import API_KEY, API_DATE, CACHE_DIR, DEPT_CODES

HEADERS = {
    'accept': 'application/json',
    'ucsb-api-key': API_KEY
} if API_KEY else {'accept': 'application/json'}


def get_cache_path(class_code: str) -> Path:
    """Get the cache file path for a class code"""
    return CACHE_DIR / f"{class_code}.json"


def fetch_course_data(class_code: str) -> Optional[Dict]:
    """Fetch course data from UCSB API"""
    if not API_KEY:
        return None
    
    url = f"https://api.ucsb.edu/academics/curriculums/v3/classes/{API_DATE}/{class_code}?includeClassSections=true"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and "courseId" in data:
                # Cache the result
                cache_path = get_cache_path(class_code)
                with open(cache_path, 'w') as f:
                    json.dump(data, f, indent=2)
                return data
    except Exception as e:
        print(f"Error fetching course {class_code}: {e}")
    
    return None


def get_course_data(class_code: str, use_cache: bool = True) -> Optional[Dict]:
    """Get course data, using cache if available"""
    if use_cache:
        cache_path = get_cache_path(class_code)
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
    
    return fetch_course_data(class_code)


def search_courses(query: str = "", department: str = "", limit: int = 100) -> List[Dict]:
    """
    Search courses based on query and department
    Returns a list of unique course summaries grouped by courseId (limited to 'limit' results)
    """
    results_dict = {}  # Key: courseId, Value: course summary
    query_lower = query.lower() if query else ""
    dept_upper = department.upper() if department else ""
    
    # Build a flat list of all course codes with department info
    course_codes = []
    for dept, codes in DEPT_CODES:
        if not dept_upper or dept == dept_upper:
            for code in codes:
                course_codes.append((dept, code))
    
    # Fetch and filter courses (only use cached data for performance)
    for dept, code in course_codes:
        if len(results_dict) >= limit:
            break
            
        course_data = get_course_data(code, use_cache=True)
        if not course_data:
            continue
        
        course_id = course_data.get("courseId", "")
        title = course_data.get("title", "")
        subject_area = course_data.get("subjectArea", "")
        
        # Skip if we already have this courseId
        if course_id in results_dict:
            continue
        
        # Filter by query
        if query_lower:
            search_text = f"{subject_area} {course_id} {title}".lower()
            if query_lower not in search_text:
                continue
        
        # Extract basic info for search results
        course_summary = {
            "courseId": course_id,
            "title": title,
            "subjectArea": subject_area,
            "units": course_data.get("unitsFixed", course_data.get("unitsVariableHigh")),
            "department": dept
        }
        
        results_dict[course_id] = course_summary
    
    return list(results_dict.values())


def get_course_by_id(course_id: str) -> Optional[Dict]:
    """Get course data by courseId (finds the first matching enroll code)"""
    # Normalize course_id for comparison - remove all extra whitespace
    def normalize_course_id(cid):
        if not cid:
            return ""
        # Replace multiple spaces with single space, then strip
        import re
        return re.sub(r'\s+', ' ', cid.strip())
    
    course_id_normalized = normalize_course_id(course_id)
    
    # Find first matching enroll code for this courseId
    for dept, codes in DEPT_CODES:
        for code in codes:
            course_data = get_course_data(code, use_cache=True)
            if course_data:
                course_id_from_data = normalize_course_id(course_data.get("courseId", ""))
                if course_id_from_data == course_id_normalized:
                    return course_data
    return None


def get_course_info(course_id: str) -> Optional[Dict]:
    """Get full course information including all lectures and sections"""
    course_data = get_course_by_id(course_id)
    if not course_data:
        return None
    
    # Extract and structure time information
    sections = course_data.get("classSections", [])
    
    # Separate lecture and discussion/lab sections
    # Logic: If there are multiple sections, the first one(s) are typically lectures
    # If only one section exists, it's the lecture
    # Also check for explicit "LEC" markers
    lecture_sections = []
    other_sections = []
    
    if len(sections) == 0:
        # No sections at all
        pass
    elif len(sections) == 1:
        # Only one section - it's the lecture
        lecture_sections = sections
    else:
        # Multiple sections - first section is lecture, rest are discussions/labs
        # But also check for explicit LEC markers in case structure is different
        for i, section in enumerate(sections):
            section_code = section.get("section", "")
            section_type_code = section.get("sectionTypeCode", "")
            
            # Check if explicitly marked as lecture
            is_explicit_lecture = (
                (section_code and "LEC" in section_code.upper()) or
                (section_type_code and "LEC" in section_type_code.upper())
            )
            
            if is_explicit_lecture:
                lecture_sections.append(section)
            elif i == 0:
                # First section is lecture by convention
                lecture_sections.append(section)
            else:
                other_sections.append(section)
    
    # Format time information
    def format_time_info(section):
        time_locations = section.get("timeLocations", [])
        times = []
        for time_loc in time_locations:
            days = time_loc.get("days", "").strip()
            start_time = time_loc.get("beginTime", "")
            end_time = time_loc.get("endTime", "")
            location = time_loc.get("building", "")
            if location and time_loc.get("room"):
                location += " " + time_loc.get("room")
            
            if days and start_time and end_time:
                times.append({
                    "days": days,
                    "startTime": start_time,
                    "endTime": end_time,
                    "location": location
                })
        return times
    
    # Format lecture times - include ALL lectures
    lecture_times = []
    for lec in lecture_sections:
        times = format_time_info(lec)
        # Always include lecture, even if it has no times
        lecture_times.append({
            "enrollCode": lec.get("enrollCode"),
            "section": lec.get("section"),
            "instructor": lec.get("instructors", [{}])[0].get("instructor", "") if lec.get("instructors") else "",
            "times": times if times else [],  # Ensure it's always a list
            "enrolled": lec.get("enrolledTotal", 0),
            "maxEnroll": lec.get("maxEnroll", 0)
        })
    
    # Format other section times - group by lecture if possible
    # For now, just list all sections
    section_times = []
    for sec in other_sections:
        times = format_time_info(sec)
        if times:
            section_times.append({
                "enrollCode": sec.get("enrollCode"),
                "section": sec.get("section"),
                "instructor": sec.get("instructors", [{}])[0].get("instructor", "") if sec.get("instructors") else "",
                "times": times,
                "enrolled": sec.get("enrolledTotal", 0),
                "maxEnroll": sec.get("maxEnroll", 0)
            })
    
    return {
        "courseId": course_data.get("courseId"),
        "title": course_data.get("title"),
        "subjectArea": course_data.get("subjectArea"),
        "units": course_data.get("unitsFixed", course_data.get("unitsVariableHigh")),
        "description": course_data.get("description", ""),
        "generalEducation": course_data.get("generalEducation", []),
        "lectureSections": lecture_times,
        "sections": section_times
    }


def get_section_details(lecture_enroll_code: str, section_enroll_code: Optional[str] = None) -> Optional[Dict]:
    """Get details for a specific lecture and optionally a section"""
    # Find course data by lecture enroll code
    course_data = get_course_data(lecture_enroll_code, use_cache=True)
    if not course_data:
        return None
    
    # Format time information
    def format_time_info(section):
        time_locations = section.get("timeLocations", [])
        times = []
        for time_loc in time_locations:
            days = time_loc.get("days", "").strip()
            start_time = time_loc.get("beginTime", "")
            end_time = time_loc.get("endTime", "")
            location = time_loc.get("building", "")
            if location and time_loc.get("room"):
                location += " " + time_loc.get("room")
            
            if days and start_time and end_time:
                times.append({
                    "days": days,
                    "startTime": start_time,
                    "endTime": end_time,
                    "location": location
                })
        return times
    
    # Find the lecture section
    sections = course_data.get("classSections", [])
    lecture_section = None
    section_data = None
    
    for section in sections:
        if section.get("enrollCode") == lecture_enroll_code:
            lecture_section = section
        if section_enroll_code and section.get("enrollCode") == section_enroll_code:
            section_data = section
    
    if not lecture_section:
        return None
    
    lecture_times = format_time_info(lecture_section)
    section_times = format_time_info(section_data) if section_data else []
    
    return {
        "courseId": course_data.get("courseId"),
        "title": course_data.get("title"),
        "subjectArea": course_data.get("subjectArea"),
        "units": course_data.get("unitsFixed", course_data.get("unitsVariableHigh")),
        "lecture": {
            "enrollCode": lecture_enroll_code,
            "section": lecture_section.get("section"),
            "instructor": lecture_section.get("instructors", [{}])[0].get("instructor", "") if lecture_section.get("instructors") else "",
            "times": lecture_times,
            "enrolled": lecture_section.get("enrolledTotal", 0),
            "maxEnroll": lecture_section.get("maxEnroll", 0)
        },
        "section": {
            "enrollCode": section_enroll_code,
            "section": section_data.get("section") if section_data else None,
            "instructor": section_data.get("instructors", [{}])[0].get("instructor", "") if section_data and section_data.get("instructors") else "",
            "times": section_times,
            "enrolled": section_data.get("enrolledTotal", 0) if section_data else 0,
            "maxEnroll": section_data.get("maxEnroll", 0) if section_data else 0
        } if section_enroll_code else None
    }


def has_time_conflict(time1: Dict, time2: Dict) -> bool:
    """Check if two time ranges overlap"""
    def time_to_minutes(time_str: str) -> int:
        if not time_str:
            return 0
        parts = time_str.split(':')
        if len(parts) != 2:
            return 0
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, TypeError):
            return 0
    
    days1 = set(time1.get("days", "").replace(" ", ""))
    days2 = set(time2.get("days", "").replace(" ", ""))
    
    # Check if they share any days
    if not days1.intersection(days2):
        return False
    
    start1 = time_to_minutes(time1.get("startTime", ""))
    end1 = time_to_minutes(time1.get("endTime", ""))
    start2 = time_to_minutes(time2.get("startTime", ""))
    end2 = time_to_minutes(time2.get("endTime", ""))
    
    if not all([start1, end1, start2, end2]):
        return False
    
    # Check if time ranges overlap (exclusive of exact boundaries)
    return start1 < end2 and end1 > start2


def check_times_conflict(times_list: List[Dict], selected_times: List[Dict]) -> bool:
    """Check if any time in times_list conflicts with any selected_time"""
    for time_info in times_list:
        for selected_time in selected_times:
            if has_time_conflict(time_info, selected_time):
                return True
    return False


def filter_courses_by_schedule(courses: List[Dict], selected_courses: List[Dict]) -> List[Dict]:
    """
    Filter courses that don't conflict with selected courses.
    A course passes if there's at least one complete lecture+section combination
    (or just lecture if no sections) that has no time conflicts.
    Returns courses with conflict-free combinations metadata.
    """
    if not selected_courses:
        return courses
    
    # Build list of selected times from all selected courses
    selected_times = []
    for course in selected_courses:
        if course.get("lecture") and course["lecture"].get("times"):
            selected_times.extend(course["lecture"]["times"])
        if course.get("section") and course["section"].get("times"):
            selected_times.extend(course["section"]["times"])
    
    if not selected_times:
        return courses
    
    # Filter courses - check if there's at least one valid lecture+section combination
    filtered = []
    for course in courses:
        course_info = get_course_info(course.get("courseId"))
        if not course_info:
            continue
        
        lectures = course_info.get("lectureSections", [])
        sections = course_info.get("sections", [])
        
        # If no lectures, skip this course
        if not lectures:
            continue
        
        # Find all conflict-free combinations
        conflict_free_combinations = []
        
        # Check each lecture
        for lecture_idx, lecture in enumerate(lectures):
            lecture_times = lecture.get("times", [])
            
            # Skip lectures with no times (TBA) - can't verify conflicts
            if not lecture_times:
                # If no sections, consider TBA lectures as valid
                if not sections:
                    conflict_free_combinations.append({
                        "lectureIndex": lecture_idx,
                        "sectionIndex": None
                    })
                continue
            
            # Check if lecture conflicts
            lecture_conflicts = check_times_conflict(lecture_times, selected_times)
            
            if lecture_conflicts:
                # This lecture conflicts, try next lecture
                continue
            
            # Lecture doesn't conflict - now check sections
            if not sections:
                # No sections needed - this lecture works!
                conflict_free_combinations.append({
                    "lectureIndex": lecture_idx,
                    "sectionIndex": None
                })
                continue
            
            # Check each section for conflicts
            for section_idx, section in enumerate(sections):
                section_times = section.get("times", [])
                
                # If section has no times (TBA), consider it valid
                if not section_times:
                    conflict_free_combinations.append({
                        "lectureIndex": lecture_idx,
                        "sectionIndex": section_idx
                    })
                    continue
                
                # Check if section conflicts
                section_conflicts = check_times_conflict(section_times, selected_times)
                
                if not section_conflicts:
                    # Found a valid lecture+section combination!
                    conflict_free_combinations.append({
                        "lectureIndex": lecture_idx,
                        "sectionIndex": section_idx
                    })
        
        # Only include course if it has at least one conflict-free combination
        if conflict_free_combinations:
            # Add conflict-free combinations metadata to course
            course_with_metadata = course.copy()
            course_with_metadata["_conflictFreeCombinations"] = conflict_free_combinations
            filtered.append(course_with_metadata)
    
    return filtered


def get_departments() -> List[str]:
    """Get list of all departments"""
    return [dept[0] for dept in DEPT_CODES]
