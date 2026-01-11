# Scheduling conflict resolver: checks if any enroll codes in group B conflict with group A

import json
import requests
from pathlib import Path

# Use fetch_class_data from api_data_setup.py everywhere we need course section data

MY_API_KEY = input("Enter API key: ")
headers = {
    'accept': 'text/plain',
    'ucsb-api-key': MY_API_KEY
}

# checks if the class code is valid
def fetch_class_data(class_code):
    date = "20261"
    url = f"https://api.ucsb.edu/academics/curriculums/v3/classes/{date}/{class_code}?includeClassSections=true"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return None
def get_course_section_times(enroll_code):
    """
    Fetch scheduled meeting times for a lecture or section given its enroll code.
    Always fetch using fetch_class_data for accurate info.
    """
    # fetch_class_data expects class_code, which for this use is the enroll_code
    data = fetch_class_data(str(enroll_code))
    if not data:
        return []
    # If top-level is a course, look for the correct section
    if "classSections" in data:
        for section in data.get("classSections", []):
            if str(section.get("enrollCode")) == str(enroll_code):
                return get_times_from_section(section)
        return []
    # In some edge cases, the data might be a section object already
    return get_times_from_section(data)

def get_course_section_info(enroll_code):
    """
    Fetch and return the section info dict for this enroll_code, or None.
    Always fetch using fetch_class_data.
    """
    data = fetch_class_data(str(enroll_code))
    if not data:
        return None
    if "classSections" in data:
        for section in data.get("classSections", []):
            if str(section.get("enrollCode")) == str(enroll_code):
                return section
        return None
    # In some rare cases, the data itself might be a section dict
    return data if str(data.get("enrollCode", "")) == str(enroll_code) else None

def get_times_from_section(section):
    """Return a list of dicts, each with days, start, end from the section JSON."""
    out = []
    for tl in section.get("timeLocations", []):
        days = tl.get("days", "")
        start = tl.get("beginTime", "")
        end = tl.get("endTime", "")
        if days and start and end:
            out.append({
                "days": days,
                "start": start,
                "end": end
            })
    return out

def has_conflict(times1, times2):
    """Check if any time in times1 conflicts with any in times2."""
    for t1 in times1:
        for t2 in times2:
            if times_overlap(t1, t2):
                return True
    return False

def days_overlap(days1, days2):
    """Return True if there are any shared day characters."""
    return bool(set(days1.replace(" ", "")) & set(days2.replace(" ", "")))

def time_to_minutes(timestr):
    """Expects 'HH:MM'."""
    try:
        h, m = map(int, timestr.split(":"))
        return h * 60 + m
    except Exception:
        return None

def times_overlap(t1, t2):
    # First, days must overlap
    if not days_overlap(t1["days"], t2["days"]):
        return False
    # Second, times must overlap
    s1 = time_to_minutes(t1["start"])
    e1 = time_to_minutes(t1["end"])
    s2 = time_to_minutes(t2["start"])
    e2 = time_to_minutes(t2["end"])
    if None in (s1, e1, s2, e2):
        return False
    return s1 < e2 and e1 > s2

def schedule_conflicts(enrolled_enroll_codes, test_enroll_codes):
    """
    Returns True if ANY enroll code in test_enroll_codes conflicts with any in enrolled_enroll_codes.
    """
    # Collect all meeting times from already-enrolled
    enrolled_times = []
    for ec in enrolled_enroll_codes:
        enrolled_times += get_course_section_times(ec)
    # For each test code, check ALL its times against ALL enrolled_times
    for tc in test_enroll_codes:
        test_times = get_course_section_times(tc)
        if not test_times:
            continue  # No meeting times, can't conflict
        if has_conflict(test_times, enrolled_times):
            return True
    return False

if __name__ == "__main__":
    # Example: these enroll codes should exist for this quarter
    enrolled_enroll_codes = ["75457", "38687", "29686"]
    test_enroll_codes = ["29686", "49106", "11601"]

    # Helper to format time as 'MWF 10:00-10:50'
    def format_times(times):
        if not times:
            return "(no meeting)"
        slotlist = []
        for t in times:
            days = t.get("days", "")
            start = t.get("start", "")
            end = t.get("end", "")
            slotlist.append(f"{days} {start}-{end}".strip())
        return "; ".join(slotlist)

    print("Enrolled codes and their meetings:")
    for ec in enrolled_enroll_codes:
        times = get_course_section_times(ec)
        title = ""
        section_type = ""
        try:
            section_info = get_course_section_info(ec)
            # Try both "courseTitle" and "title" as possible section fields
            title = section_info.get("courseTitle", "") if section_info else ""
            if not title and section_info:
                title = section_info.get("title", "")

            # Try to get type of class, typically "section" key
            if section_info and "section" in section_info:
                section_type = section_info.get("section", "")
            elif section_info and "sectionType" in section_info:
                section_type = section_info.get("sectionType", "")
        except Exception:
            pass
        print(f"  {ec}: {title} | {section_type} | {format_times(times)}")

    print("Test codes and their meetings:")
    for tc in test_enroll_codes:
        times = get_course_section_times(tc)
        title = ""
        section_type = ""
        try:
            section_info = get_course_section_info(tc)
            title = section_info.get("courseTitle", "") if section_info else ""
            if not title and section_info:
                title = section_info.get("title", "")

            if section_info and "section" in section_info:
                section_type = section_info.get("section", "")
            elif section_info and "sectionType" in section_info:
                section_type = section_info.get("sectionType", "")
        except Exception:
            pass
        print(f"  {tc}: {title} | {section_type} | {format_times(times)}")

    if schedule_conflicts(enrolled_enroll_codes, test_enroll_codes):
        print("There is a conflict between the enrolled and test codes.")
    else:
        print("No conflict between the enrolled and test codes.")

# Usage:
#   schedule_conflicts(["123456", "222333"], ["555666"])
#   returns True if "555666" conflicts with either "123456" or "222333", else False
