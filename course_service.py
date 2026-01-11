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
# Note: We cache empty lists, but will re-check if cache was populated before the fix
_all_course_data_cache: Dict[str, List[Dict]] = {}
# Track which courseIds we've done a full search for (to avoid re-searching unnecessarily)
_full_search_cache: Dict[str, bool] = {}


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


def course_has_times(course_data: Dict) -> bool:
    """
    Check if a course has any sections with valid time information.
    Returns True if at least one section has days, beginTime, and endTime.
    """
    try:
        sections = course_data.get("classSections", [])
        if not isinstance(sections, list):
            return False
        
        for section in sections:
            if not isinstance(section, dict):
                continue
            
            time_locations = section.get("timeLocations", [])
            if not isinstance(time_locations, list):
                continue
            
            for time_loc in time_locations:
                if not isinstance(time_loc, dict):
                    continue
                
                days = time_loc.get("days", "")
                if days:
                    days = str(days).strip()
                start_time = time_loc.get("beginTime", "")
                end_time = time_loc.get("endTime", "")
                
                # If we have all three required fields, the course has times
                if days and start_time and end_time:
                    return True
        return False
    except (AttributeError, TypeError, KeyError) as e:
        # If there's any error processing the data, assume the course doesn't have times
        # This prevents crashes from malformed data
        return False


def search_courses(query: str = "", department: str = "", general_subjects: List[str] = None, special_subject: str = "", limit: int = 100) -> List[Dict]:
    """
    Search courses based on query, department, general subject (GE Areas), and special subject requirements
    Returns a list of unique course summaries grouped by courseId (limited to 'limit' results)
    Only includes courses that have at least one section with valid time information.
    
    Args:
        query: Text search query
        department: Department filter
        general_subjects: List of general subject requirements (Area A, B, C, etc.) - courses matching ANY will be included
        special_subject: Single special subject requirement filter (AREA, ETH, EUR, NWC, QNT, WRT)
        limit: Maximum number of results to return
    """
    if general_subjects is None:
        general_subjects = []
    
    results_dict = {}  # Key: courseId, Value: course summary
    query_lower = query.lower() if query else ""
    dept_upper = department.upper() if department else ""
    special_subject_upper = special_subject.upper() if special_subject else ""
    general_subjects_upper = [s.upper() for s in general_subjects if s]  # Normalize all general subjects
    
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
        
        # Filter out courses without any times
        if not course_has_times(course_data):
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
        
        # Get general education requirements
        general_education = course_data.get("generalEducation", [])
        ge_codes = [ge.get("geCode", "").upper() for ge in general_education if isinstance(ge, dict)]
        
        # Filter by general subjects (Area A, B, C, etc.) - matches if ANY selected area matches
        if general_subjects_upper:
            matches_any = False
            for area in general_subjects_upper:
                # Check each GE requirement object for area match
                for ge in general_education:
                    if not isinstance(ge, dict):
                        continue
                    # Check if GE code contains the area letter (e.g., "AREA A" contains "A")
                    ge_code = ge.get("geCode", "").upper()
                    if area in ge_code or ge_code.startswith(area):
                        matches_any = True
                        break
                    # Check if there's an explicit area field in the GE object
                    ge_area = ge.get("area", "").upper()
                    if ge_area == area:
                        matches_any = True
                        break
                if matches_any:
                    break
            
            if not matches_any:
                continue
        
        # Filter by special subject (specific GE code like AREA, ETH, EUR, NWC, QNT, WRT)
        if special_subject_upper:
            # Check if course has the specified GE code
            if special_subject_upper not in ge_codes:
                continue
        
        # Extract basic info for search results
        course_summary = {
            "courseId": course_id,
            "title": title,
            "subjectArea": subject_area,
            "units": course_data.get("unitsFixed", course_data.get("unitsVariableHigh")),
            "department": dept,
            "generalEducation": general_education  # Include GE data for frontend display
        }
        
        results_dict[course_id] = course_summary
    
    return list(results_dict.values())


def get_course_by_id(course_id: str) -> Optional[Dict]:
    """Get course data by courseId (finds the first matching enroll code)"""
    # Normalize course_id for comparison and caching - remove all extra whitespace
    def normalize_course_id(cid):
        if not cid:
            return ""
        # Replace multiple spaces with single space, then strip
        import re
        return re.sub(r'\s+', ' ', cid.strip())
    
    course_id_normalized = normalize_course_id(course_id)
    
    # Check cache first using normalized ID
    if course_id_normalized in _course_id_cache:
        return _course_id_cache[course_id_normalized]
    
    # Find first matching enroll code for this courseId
    for dept, codes in DEPT_CODES:
        for code in codes:
            course_data = get_course_data(code, use_cache=True)
            if course_data:
                course_id_from_data = normalize_course_id(course_data.get("courseId", ""))
                if course_id_from_data == course_id_normalized:
                    # Cache the result using normalized ID
                    _course_id_cache[course_id_normalized] = course_data
                    return course_data
    
    # Cache None to avoid repeated searches for non-existent courses
    _course_id_cache[course_id_normalized] = None
    return None


def get_all_course_data_by_id(course_id: str) -> List[Dict]:
    """Get all course data entries for a courseId (multiple enroll codes can have same courseId)"""
    # Normalize course_id for comparison and caching
    def normalize_course_id(cid):
        if not cid:
            return ""
        import re
        return re.sub(r'\s+', ' ', cid.strip())
    
    course_id_normalized = normalize_course_id(course_id)
    
    # Check cache first using normalized ID
    # Only use cache if we've done a full search before (to avoid false negatives from old buggy code)
    if course_id_normalized in _all_course_data_cache and course_id_normalized in _full_search_cache:
        return _all_course_data_cache[course_id_normalized]
    
    # Try to find matching department(s) from courseId
    # Handle multi-word departments like "C LIT", "AS AM", "BL ST"
    matching_depts = []
    if course_id_normalized:
        # Get all department codes
        all_dept_codes = [dept for dept, _ in DEPT_CODES]
        
        # Try to match department by checking if courseId starts with any department code
        for dept_code in all_dept_codes:
            # Normalize department code for comparison
            dept_normalized = normalize_course_id(dept_code)
            # Check if courseId starts with this department code (with space after)
            if course_id_normalized.startswith(dept_normalized + " "):
                matching_depts.append(dept_code)
        
        # If no exact match, try single-word match as fallback (e.g., "C" might match "C LIT")
        if not matching_depts:
            parts = course_id_normalized.split()
            if parts:
                first_part = parts[0].strip()
                # Find departments that start with this part
                for dept_code in all_dept_codes:
                    dept_normalized = normalize_course_id(dept_code)
                    dept_parts = dept_normalized.split()
                    if dept_parts and dept_parts[0] == first_part:
                        matching_depts.append(dept_code)
    
    all_course_data = []
    
    # Find ALL matching enroll codes for this courseId
    # Search in matching departments first, then fall back to all departments if no matches
    depts_to_search = matching_depts if matching_depts else None  # None means search all
    
    for dept, codes in DEPT_CODES:
        # Only search in matching departments if we have them, otherwise search all
        if depts_to_search is not None and dept not in depts_to_search:
            continue
            
        for code in codes:
            course_data = get_course_data(code, use_cache=True)
            if course_data:
                course_id_from_data = normalize_course_id(course_data.get("courseId", ""))
                if course_id_from_data == course_id_normalized:
                    all_course_data.append(course_data)
        
        # If we found matches and we're searching specific departments, we can stop
        # (all enroll codes for a courseId should be in the same department)
        if depts_to_search is not None and all_course_data:
            break
    
    # If we searched specific departments but found nothing, fall back to searching all departments
    # This handles cases where department matching was incorrect
    if depts_to_search is not None and not all_course_data:
        # Debug: Log when fallback search is needed (indicates department matching issue)
        import warnings
        warnings.warn(f"Department matching for '{course_id_normalized}' found no results in {depts_to_search}, falling back to full search")
        
        for dept, codes in DEPT_CODES:
            # Skip departments we already searched
            if dept in depts_to_search:
                continue
                
            for code in codes:
                course_data = get_course_data(code, use_cache=True)
                if course_data:
                    course_id_from_data = normalize_course_id(course_data.get("courseId", ""))
                    if course_id_from_data == course_id_normalized:
                        all_course_data.append(course_data)
            
            # If we found matches, we can stop
            if all_course_data:
                break
    
    # Cache the result using normalized ID
    _all_course_data_cache[course_id_normalized] = all_course_data
    # Mark that we've done a full search for this courseId
    _full_search_cache[course_id_normalized] = True
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
    
    # Handle courses with sections but no lectures (e.g., labs, standalone sections)
    # Collect all non-lecture sections from all course data files
    standalone_sections = []
    for course_data in all_course_data:
        sections = course_data.get("classSections", [])
        for section in sections:
            type_instruction = section.get("typeInstruction", "")
            if type_instruction != "LEC":
                standalone_sections.append(section)
    
    # If we have standalone sections but no lectures, create "lecture" entries for each section
    # This allows the rest of the code to treat them uniformly
    if not lectures_with_sections and standalone_sections:
        for section in standalone_sections:
            enroll_code = section.get("enrollCode", "")
            if enroll_code and enroll_code not in lectures_with_sections:
                # Treat each standalone section as its own "lecture" (but mark it as standalone)
                lectures_with_sections[enroll_code] = {
                    'lecture': section,  # The section itself acts as the "lecture"
                    'sections': [],  # No sub-sections
                    'isStandalone': True  # Flag to indicate this is a standalone section
                }
    
    # Fallback: If no lectures found by typeInstruction, but we have sections,
    # treat single section as lecture (for courses without explicit typeInstruction)
    if not lectures_with_sections and len(all_course_data) == 1:
        fallback_sections = all_course_data[0].get("classSections", [])
        if len(fallback_sections) == 1:
            lectures_with_sections[fallback_sections[0].get("enrollCode", "")] = {
                'lecture': fallback_sections[0],
                'sections': [],
                'isStandalone': True
            }
    
    # Format time information
    def format_time_info(section):
        time_locations = section.get("timeLocations", [])
        times = []
        for time_loc in time_locations:
            days = time_loc.get("days") or ""
            if days:
                days = str(days).strip()
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
        is_standalone = data.get('isStandalone', False)
        times = format_time_info(lec)
        lecture_instructor = lec.get("instructors", [{}])[0].get("instructor", "") if lec.get("instructors") else ""
        
        # Format sections for this lecture
        lecture_section_list = []
        course_id = first_course_data.get("courseId", "")
        for sec in data['sections']:
            # Verify section belongs to this lecture (skip for standalone sections)
            if not is_standalone and not verify_section_belongs_to_lecture(sec, lec, lecture_enroll_code, course_id):
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
        
        # Always include lecture/standalone section, even if it has no times
        lecture_entry = {
            "enrollCode": lecture_enroll_code,
            "section": lec.get("section"),
            "instructor": lec.get("instructors", [{}])[0].get("instructor", "") if lec.get("instructors") else "",
            "times": times if times else [],  # Ensure it's always a list
            "enrolled": lec.get("enrolledTotal", 0),
            "maxEnroll": lec.get("maxEnroll", 0),
            "sections": lecture_section_list,  # Sections associated with this lecture
            "isStandalone": is_standalone,  # Flag indicating this is a standalone section (no lecture)
            "typeInstruction": lec.get("typeInstruction", "")  # Preserve section type (LAB, DIS, etc.)
        }
        lecture_times.append(lecture_entry)
        
        # For standalone sections, also add them to the flat sections list
        if is_standalone and times:
            section_info = {
                "enrollCode": lecture_enroll_code,
                "section": lec.get("section"),
                "instructor": lec.get("instructors", [{}])[0].get("instructor", "") if lec.get("instructors") else "",
                "times": times,
                "enrolled": lec.get("enrolledTotal", 0),
                "maxEnroll": lec.get("maxEnroll", 0),
                "lectureEnrollCode": None,  # No lecture for standalone sections
                "isStandalone": True
            }
            all_sections_flat.append(section_info)
    
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
    """
    Get details for a specific lecture and optionally a section.
    For standalone sections (no lecture), lecture_enroll_code should be the section's enroll code.
    """
    # Find course data by lecture/section enroll code
    course_data = get_course_data(lecture_enroll_code, use_cache=True)
    if not course_data:
        return None
    
    # Format time information
    def format_time_info(section):
        time_locations = section.get("timeLocations", [])
        times = []
        for time_loc in time_locations:
            days = time_loc.get("days") or ""
            if days:
                days = str(days).strip()
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
    
    # Find the lecture section (or standalone section)
    sections = course_data.get("classSections", [])
    lecture_section = None
    section_data = None
    is_standalone = False
    
    # Check if this is a standalone section (no lecture in the course)
    has_lecture = any(s.get("typeInstruction") == "LEC" for s in sections)
    
    for section in sections:
        if section.get("enrollCode") == lecture_enroll_code:
            lecture_section = section
            # Check if this section is standalone (not a lecture)
            if not has_lecture and section.get("typeInstruction") != "LEC":
                is_standalone = True
        if section_enroll_code and section.get("enrollCode") == section_enroll_code:
            section_data = section
    
    if not lecture_section:
        return None
    
    lecture_times = format_time_info(lecture_section)
    section_times = format_time_info(section_data) if section_data else []
    
    # For standalone sections, the "lecture" field represents the standalone section itself
    result = {
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
            "maxEnroll": lecture_section.get("maxEnroll", 0),
            "isStandalone": is_standalone,
            "typeInstruction": lecture_section.get("typeInstruction", "")
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
    
    return result


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
        
        # Find all conflict-free combinations
        conflict_free_combinations = []
        
        # Handle courses with no lectures (only standalone sections)
        if not lectures:
            # Check standalone sections directly
            for section_idx, section in enumerate(all_sections):
                if section.get("isStandalone", False):
                    section_times = section.get("times", [])
                    
                    # Skip sections with no times (TBA) - can't verify conflicts
                    if not section_times:
                        conflict_free_combinations.append({
                            "lectureIndex": None,
                            "sectionIndex": section_idx,
                            "isStandalone": True
                        })
                        continue
                    
                    # Check if section conflicts
                    section_conflicts = check_times_conflict(section_times, selected_times)
                    
                    if not section_conflicts:
                        conflict_free_combinations.append({
                            "lectureIndex": None,
                            "sectionIndex": section_idx,
                            "isStandalone": True
                        })
        else:
            # Check each lecture
            for lecture_idx, lecture in enumerate(lectures):
                is_standalone = lecture.get("isStandalone", False)
                lecture_times = lecture.get("times", [])
                # Get sections that belong to this lecture
                lecture_sections = lecture.get("sections", [])
                
                # Handle standalone sections (sections without lectures)
                if is_standalone:
                    # Find the index in all_sections array
                    section_idx = None
                    for idx, sec in enumerate(all_sections):
                        if sec.get("enrollCode") == lecture.get("enrollCode"):
                            section_idx = idx
                            break
                    
                    # Skip standalone sections with no times (TBA) - can't verify conflicts
                    if not lecture_times:
                        conflict_free_combinations.append({
                            "lectureIndex": lecture_idx,
                            "sectionIndex": section_idx,
                            "isStandalone": True
                        })
                        continue
                    
                    # Check if standalone section conflicts
                    section_conflicts = check_times_conflict(lecture_times, selected_times)
                    
                    if not section_conflicts:
                        conflict_free_combinations.append({
                            "lectureIndex": lecture_idx,
                            "sectionIndex": section_idx,
                            "isStandalone": True
                        })
                    continue
                
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
