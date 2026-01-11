import json
import os
from datetime import datetime

# --- 1. AUTO-SETUP FOLDERS ---
# Define folder paths for the student's current schedule and potential new classes
CURRENT_CLASSES_FOLDER = "current_classes"
POTENTIAL_CLASSES_FOLDER = "potential_classes"

# --- 2. CONFIGURATION ---
# Global toggles to filter results by specific subjects or requirements
TARGET_SUBJECT = False 
TARGET_GE = False 
REQUIRE_ONLINE = None

# --- 3. CORE LOGIC FUNCTIONS ---

def is_overlapping(start1, end1, start2, end2):
    """Checks if two time ranges (HH:MM) overlap by comparing datetime objects."""
    fmt = "%H:%M"
    try:
        s1, e1 = datetime.strptime(start1, fmt), datetime.strptime(end1, fmt)
        s2, e2 = datetime.strptime(start2, fmt), datetime.strptime(end2, fmt)
        return s1 < e2 and e1 > s2
    except: 
        return False

def generate_blackout_from_folder(folder_path):
    """Scans 'current_classes' folder to map out exactly when the student is busy."""
    blackout = {"M": [], "T": [], "W": [], "R": [], "F": []}
    files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
    for filename in files:
        with open(os.path.join(folder_path, filename), 'r') as f:
            data = json.load(f)
            # Drill down into class sections and their meeting times to build the blackout wall
            for section in data.get("classSections", []):
                for loc in section.get("timeLocations", []):
                    days = (loc.get("days") or "").strip()
                    start, end = loc.get("beginTime"), loc.get("endTime")
                    if start and end:
                        for day in days:
                            if day in blackout:
                                blackout[day].append((start, end))
    return blackout

def has_time_conflict(section, blackout_schedule):
    """Compares a specific section's meeting times against the student's busy schedule."""
    time_locs = section.get("timeLocations") or []
    for loc in time_locs:
        days, start, end = (loc.get("days") or "").strip(), loc.get("beginTime"), loc.get("endTime")
        if not all([days, start, end]): 
            continue
        # Loop through each day the section meets and check for any overlap with blackout times
        for day in days:
            if day in blackout_schedule:
                for b_start, b_end in blackout_schedule[day]:
                    if is_overlapping(start, end, b_start, b_end):
                        return True, f"Conflict on {day}"
    return False, ""

def check_class(data, blackout):
    """The main gatekeeper: evaluates if a course is eligible based on units, subjects, and availability."""
    course_id = data.get("courseId", "Unknown")
    
    # NEW: Filter out classes that have variable units (e.g., 1.0-4.0 units)
    if data.get("unitsVariableHigh") is not None:
        return False, [], ["Variable Units"]

    # Optional filter to only look for specific departments (e.g., 'PHYS')
    if TARGET_SUBJECT and (data.get("subjectArea") or "").strip() != TARGET_SUBJECT:
        return False, [], ["Wrong Subject"]
    
    valid_codes = []
    rejection_counts = {"Full": 0, "Conflict": 0}
    
    # Iterate through every section of the course to find those that are both open and conflict-free
    for section in data.get("classSections", []):
        enrolled, max_cap = section.get("enrolledTotal") or 0, section.get("maxEnroll") or 0
        if enrolled >= max_cap:
            rejection_counts["Full"] += 1
            continue
            
        conflict, _ = has_time_conflict(section, blackout)
        if conflict:
            rejection_counts["Conflict"] += 1
            continue
            
        # Store the 'enrollCode' of sections that passed both the 'Full' and 'Conflict' check
        valid_codes.append(section.get("enrollCode"))
            
    # If no sections worked, summarize why (e.g., '3 Full, 1 Conflict')
    reasons = [f"{v} {k}" for k, v in rejection_counts.items() if v > 0]
    return (True if valid_codes else False), valid_codes, reasons

# --- 4. MAIN EXECUTION ---

# Step 1: Create the master busy-schedule for the current student
current_blackout = generate_blackout_from_folder(CURRENT_CLASSES_FOLDER)

# Initialize storage for passing/failing course information
true_array = []
false_array = []
true_modified_json = []

# Identify all potential JSON files to be analyzed
potential_files = [f for f in os.listdir(POTENTIAL_CLASSES_FOLDER) if f.endswith(".json")]

# Process each file in the potential classes folder
for filename in potential_files:
    path = os.path.join(POTENTIAL_CLASSES_FOLDER, filename)
    with open(path, 'r') as f:
        data = json.load(f)
        course_id = data.get("courseId", "Unknown")
        
        # Run the primary check to see if the course is a viable option
        works, sections, reasons = check_class(data, current_blackout)
        
        if works:
            print(f"✅ {course_id} WORKS!")
            
            all_sections = data.get("classSections", [])
            lecture_info = {}
            
            # Identify if we have a Lecture + Section structure
            has_lecture = len(all_sections) > 1
            
            if has_lecture:
                lec = all_sections[0]
                lec_times = []
                for loc in lec.get("timeLocations", []):
                    lec_times.append(f"{loc.get('days','').strip()} {loc.get('beginTime')}-{loc.get('endTime')}")
                
                lecture_info = {
                    "lectureCode": lec.get("enrollCode"),
                    "lectureTime": " | ".join(lec_times)
                }

            # Build the modified data entry
            mod_data = data.copy()
            mod_data["lectureDetails"] = lecture_info 
            
            # --- FIX: FILTER OUT THE LECTURE FROM SECTION LISTS ---
            # If there's a lecture, we only care about sections starting from index 1
            # If there's no lecture, we use index 0
            search_start_index = 1 if has_lecture else 0
            actual_sections_only = all_sections[search_start_index:]
            
            # Only include codes in 'passingEnrollCodes' if they are NOT the lecture code
            clean_passing_codes = [c for c in sections if c != lecture_info.get("lectureCode")]
            mod_data["passingEnrollCodes"] = clean_passing_codes
            
            # Only include times in 'sectionTimesSummary' if they are NOT the lecture
            readable_times = {} 
            for s in actual_sections_only:
                code = s.get("enrollCode")
                if code in clean_passing_codes:
                    t_list = [f"{l.get('days','').strip()} {l.get('beginTime')}-{l.get('endTime')}" for l in s.get("timeLocations", [])]
                    readable_times[code] = " | ".join(t_list)
            
            mod_data["sectionTimesSummary"] = readable_times
            
            true_array.append(course_id)
            true_modified_json.append(mod_data)
        else:
            # Provide feedback in the terminal for why a class was rejected
            print(f"❌ {course_id} REJECTED ({', '.join(reasons)})")
            false_array.append(course_id)

# --- 5. EXPORT ---
# Save only the 'Passing' courses with all the new metadata into a final JSON file
with open("filtered_courses.json", "w") as f:
    json.dump(true_modified_json, f, indent=4)

print(f"\n📂 Exported {len(true_modified_json)} courses to 'filtered_courses.json'")