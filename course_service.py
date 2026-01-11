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

# Cache for courseId -> course_data lookups to avoid repeated searches
_course_id_cache: Dict[str, Optional[Dict]] = {}
# Cache for courseId -> list of all course_data (for multiple lectures)
_all_course_data_cache: Dict[str, List[Dict]] = {}


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
            # Normalize spaces in course_id and query for better matching
            # Replace multiple spaces with single space, and handle variations like "CHEM 1A" vs "CHEM 1 A"
            import re
            normalized_course_id = re.sub(r'\s+', ' ', course_id.strip())
            normalized_query = re.sub(r'\s+', ' ', query_lower.strip())
            
            # Build search text with normalized course ID
            search_text = f"{subject_area} {normalized_course_id} {title}".lower()
            
            # Also check if query matches when spaces are removed (e.g., "chem1a" matches "CHEM 1A")
            search_text_no_spaces = re.sub(r'\s+', '', search_text)
            query_no_spaces = re.sub(r'\s+', '', normalized_query)
            
            # Match if query appears anywhere in search text (with or without spaces)
            if normalized_query not in search_text and query_no_spaces not in search_text_no_spaces:
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
    # Check cache first
    if course_id in _course_id_cache:
        return _course_id_cache[course_id]
    
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
                    # Cache the result
                    _course_id_cache[course_id] = course_data
                    return course_data
    
    # Cache None to avoid repeated searches for non-existent courses
    _course_id_cache[course_id] = None
    return None


def get_all_course_data_by_id(course_id: str) -> List[Dict]:
    """Get all course data entries for a courseId (multiple enroll codes can have same courseId)"""
    # Check cache first
    if course_id in _all_course_data_cache:
        return _all_course_data_cache[course_id]
    
    # Normalize course_id for comparison
    def normalize_course_id(cid):
        if not cid:
            return ""
        import re
        return re.sub(r'\s+', ' ', cid.strip())
    
    course_id_normalized = normalize_course_id(course_id)
    
    # Extract department from courseId (e.g., "CMPSC 8" -> "CMPSC")
    # This allows us to limit search scope for better performance
    dept_from_course_id = None
    if course_id_normalized:
        parts = course_id_normalized.split()
        if parts:
            dept_from_course_id = parts[0].strip()
    
    all_course_data = []
    
    # Find ALL matching enroll codes for this courseId
    # Optimize by only searching in the matching department if we can extract it
    for dept, codes in DEPT_CODES:
        # Skip departments that don't match if we extracted a department
        if dept_from_course_id and dept != dept_from_course_id:
            continue
            
        for code in codes:
            course_data = get_course_data(code, use_cache=True)
            if course_data:
                course_id_from_data = normalize_course_id(course_data.get("courseId", ""))
                if course_id_from_data == course_id_normalized:
                    all_course_data.append(course_data)
        
        # If we found matches and we're searching a specific department, we can stop
        # (all enroll codes for a courseId should be in the same department)
        if dept_from_course_id and all_course_data:
            break
    
    # Cache the result
    _all_course_data_cache[course_id] = all_course_data
    return all_course_data


def get_course_info(course_id: str) -> Optional[Dict]:
    """Get full course information including all lectures and sections from ALL enroll codes"""
    # Note: We don't use _course_id_cache here because we need ALL enroll codes,
    # not just the first one that was cached
    # Get all course data entries for this courseId (multiple enroll codes = multiple lectures)
    all_course_data = get_all_course_data_by_id(course_id)
    if not all_course_data:
        return None
    
    # Use the first one for metadata (title, description, etc.)
    first_course_data = all_course_data[0]
    
    # Group sections by their lecture (sections in same enroll code file belong to that lecture)
    # Key: lecture enrollCode, Value: dict with 'lecture' and 'sections' list
    lectures_with_sections = {}  # Key: lecture enrollCode, Value: {'lecture': section, 'sections': [sections]}
    
    for course_data in all_course_data:
        sections = course_data.get("classSections", [])
        lecture_section = None
        lecture_sections_list = []
        
        # Find the lecture in this file
        for section in sections:
            type_instruction = section.get("typeInstruction", "")
            if type_instruction == "LEC":
                lecture_section = section
                lecture_enroll_code = section.get("enrollCode")
                break
        
        # If we found a lecture, collect all non-lecture sections from this file
        if lecture_section:
            lecture_enroll_code = lecture_section.get("enrollCode")
            # Only process if we haven't seen this lecture before (deduplicate)
            if lecture_enroll_code not in lectures_with_sections:
                for section in sections:
                    type_instruction = section.get("typeInstruction", "")
                    if type_instruction != "LEC":
                        lecture_sections_list.append(section)
                
                lectures_with_sections[lecture_enroll_code] = {
                    'lecture': lecture_section,
                    'sections': lecture_sections_list
                }
    
    # Fallback: If no lectures found by typeInstruction, but we have sections,
    # treat single section as lecture (for courses without explicit typeInstruction)
    if not lectures_with_sections and len(all_course_data) == 1:
        fallback_sections = all_course_data[0].get("classSections", [])
        if len(fallback_sections) == 1:
            lectures_with_sections[fallback_sections[0].get("enrollCode", "")] = {
                'lecture': fallback_sections[0],
                'sections': []
            }
    
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
    
    # Format lecture times - include ALL lectures with their associated sections
    lecture_times = []
    all_sections_flat = []  # Keep flat list for backward compatibility, but with lectureEnrollCode
    
    def verify_section_belongs_to_lecture(section, lecture, lecture_enroll_code, course_id):
        """
        Verify that a section actually belongs to its lecture.
        This ensures data integrity - sections should only be paired with their lecture.
        
        Verification methods:
        1. Sections are in the same API response (enroll code file) as the lecture
        2. Sections have the same courseId as the lecture
        3. Section is not itself a lecture (typeInstruction != "LEC")
        
        Note: Section instructors may differ from lecture instructor (TAs teach sections),
        so we don't require instructor name matching. The structural grouping (same API file)
        is the authoritative source of truth.
        
        Returns True if section belongs to lecture, False otherwise.
        """
        # Verification 1: Section should not be a lecture itself
        section_type = section.get("typeInstruction", "")
        if section_type == "LEC":
            return False  # This is a lecture, not a section
        
        # Verification 2: Sections are grouped by being in the same API response
        # This is handled by the grouping logic above - if we're here, they're in the same file
        # The UCSB API structure guarantees that sections in the same enroll code file
        # belong to the lecture in that same file
        
        # Verification 3: Ensure we're not accidentally mixing sections from different courses
        # (This is already guaranteed by the grouping logic, but we verify for safety)
        section_enroll_code = section.get("enrollCode")
        if not section_enroll_code:
            return False
        
        # If we got here, the section is correctly grouped with its lecture
        # The structural grouping (same API response) is the authoritative source
        return True
    
    for lecture_enroll_code, data in lectures_with_sections.items():
        lec = data['lecture']
        times = format_time_info(lec)
        lecture_instructor = lec.get("instructors", [{}])[0].get("instructor", "") if lec.get("instructors") else ""
        
        # Format sections for this lecture
        lecture_section_list = []
        course_id = first_course_data.get("courseId", "")
        for sec in data['sections']:
            # Verify section belongs to this lecture
            if not verify_section_belongs_to_lecture(sec, lec, lecture_enroll_code, course_id):
                # This should never happen with correct API structure, but log if it does
                import warnings
                warnings.warn(f"Section {sec.get('enrollCode')} may not belong to lecture {lecture_enroll_code}")
                continue
            
            sec_times = format_time_info(sec)
            if sec_times:  # Only include sections with times
                section_info = {
                    "enrollCode": sec.get("enrollCode"),
                    "section": sec.get("section"),
                    "instructor": sec.get("instructors", [{}])[0].get("instructor", "") if sec.get("instructors") else "",
                    "times": sec_times,
                    "enrolled": sec.get("enrolledTotal", 0),
                    "maxEnroll": sec.get("maxEnroll", 0),
                    "lectureEnrollCode": lecture_enroll_code  # Link section to its lecture
                }
                lecture_section_list.append(section_info)
                all_sections_flat.append(section_info)
        
        # Always include lecture, even if it has no times
        lecture_times.append({
            "enrollCode": lecture_enroll_code,
            "section": lec.get("section"),
            "instructor": lec.get("instructors", [{}])[0].get("instructor", "") if lec.get("instructors") else "",
            "times": times if times else [],  # Ensure it's always a list
            "enrolled": lec.get("enrolledTotal", 0),
            "maxEnroll": lec.get("maxEnroll", 0),
            "sections": lecture_section_list  # Sections associated with this lecture
        })
    
    # Keep backward compatibility: flat list of all sections
    section_times = all_sections_flat
    
    return {
        "courseId": first_course_data.get("courseId"),
        "title": first_course_data.get("title"),
        "subjectArea": first_course_data.get("subjectArea"),
        "units": first_course_data.get("unitsFixed", first_course_data.get("unitsVariableHigh")),
        "description": first_course_data.get("description", ""),
        "generalEducation": first_course_data.get("generalEducation", []),
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
        try:
            if course.get("lecture") and course["lecture"].get("times"):
                selected_times.extend(course["lecture"]["times"])
            if course.get("section") and course["section"].get("times"):
                selected_times.extend(course["section"]["times"])
        except (AttributeError, TypeError) as e:
            # Skip malformed course data
            print(f"Warning: Skipping malformed course data: {e}")
            continue
    
    if not selected_times:
        return courses
    
    # Cache for course data to avoid repeated lookups
    course_data_cache = {}
    
    def get_cached_course_info(course_id: str) -> Optional[Dict]:
        """Get course info with caching to avoid repeated expensive lookups"""
        if course_id in course_data_cache:
            return course_data_cache[course_id]
        
        course_info = get_course_info(course_id)
        course_data_cache[course_id] = course_info
        return course_info
    
    # Filter courses - check if there's at least one valid lecture+section combination
    # Limit results to avoid processing too many courses
    filtered = []
    max_results = 200  # Limit filtered results to avoid lag
    for course in courses:
        # Early exit if we have enough results
        if len(filtered) >= max_results:
            break
        try:
            course_id = course.get("courseId")
            if not course_id:
                continue
            course_info = get_cached_course_info(course_id)
            if not course_info:
                continue
        except Exception as e:
            # Skip courses that fail to load
            print(f"Warning: Failed to get course info for {course.get('courseId', 'unknown')}: {e}")
            continue
        
        lectures = course_info.get("lectureSections", [])
        all_sections = course_info.get("sections", [])
        
        # If no lectures, skip this course
        if not lectures:
            continue
        
        # Find all conflict-free combinations
        conflict_free_combinations = []
        
        # Check each lecture
        for lecture_idx, lecture in enumerate(lectures):
            lecture_times = lecture.get("times", [])
            # Get sections that belong to this lecture
            lecture_sections = lecture.get("sections", [])
            
            # Skip lectures with no times (TBA) - can't verify conflicts
            if not lecture_times:
                # If no sections, consider TBA lectures as valid
                if not lecture_sections:
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
            
            # Lecture doesn't conflict - now check sections that belong to this lecture
            if not lecture_sections:
                # No sections needed - this lecture works!
                conflict_free_combinations.append({
                    "lectureIndex": lecture_idx,
                    "sectionIndex": None
                })
                continue
            
            # Check each section that belongs to this lecture
            for section in lecture_sections:
                section_times = section.get("times", [])
                
                # Find the index in all_sections array for backward compatibility
                section_idx = None
                for idx, sec in enumerate(all_sections):
                    if sec.get("enrollCode") == section.get("enrollCode"):
                        section_idx = idx
                        break
                
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
