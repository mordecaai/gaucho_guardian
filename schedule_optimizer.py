"""
Schedule Optimizer - Finds optimal lecture/section combinations for selected courses
"""
from typing import List, Dict, Optional, Tuple
from course_service import get_course_info, has_time_conflict, check_times_conflict
from itertools import product


def time_to_minutes(time_str: str) -> int:
    """Convert time string (HH:MM) to minutes since midnight"""
    if not time_str:
        return 0
    parts = time_str.split(':')
    if len(parts) != 2:
        return 0
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, TypeError):
        return 0


def get_all_times_from_schedule(schedule: Dict) -> List[Dict]:
    """Extract all time slots from a schedule (lecture + section)"""
    times = []
    if schedule.get("lecture") and schedule["lecture"].get("times"):
        times.extend(schedule["lecture"]["times"])
    if schedule.get("section") and schedule["section"].get("times"):
        times.extend(schedule["section"]["times"])
    return times


def get_all_times_from_combination(combo: Dict) -> List[Dict]:
    """Extract all time slots from a combination (lecture + section)"""
    times = []
    if combo.get("lecture") and combo["lecture"].get("times"):
        times.extend(combo["lecture"]["times"])
    if combo.get("section") and combo["section"] and combo["section"].get("times"):
        times.extend(combo["section"]["times"])
    return times


def calculate_schedule_spread(combinations: List[Dict]) -> float:
    """
    Calculate how spread out the schedule is.
    Returns a value where lower = more centered, higher = more spread out.
    """
    if not combinations:
        return 0.0
    
    all_start_times = []
    all_end_times = []
    
    for combo in combinations:
        times = get_all_times_from_combination(combo)
        for time_info in times:
            start = time_to_minutes(time_info.get("startTime", ""))
            end = time_to_minutes(time_info.get("endTime", ""))
            if start and end:
                all_start_times.append(start)
                all_end_times.append(end)
    
    if not all_start_times:
        return 0.0
    
    earliest = min(all_start_times)
    latest = max(all_end_times)
    spread = latest - earliest
    
    # Calculate variance of start times (how spread out they are)
    if len(all_start_times) > 1:
        mean_start = sum(all_start_times) / len(all_start_times)
        variance = sum((s - mean_start) ** 2 for s in all_start_times) / len(all_start_times)
        return spread + variance * 0.1  # Combine total spread with variance
    else:
        return spread


def calculate_schedule_center_score(combinations: List[Dict], preferred_start: Optional[str] = None, 
                                   preferred_end: Optional[str] = None) -> float:
    """
    Calculate how centered the schedule is around a preferred time window.
    Returns a score where higher = better centered.
    """
    if not combinations:
        return 0.0
    
    all_times = []
    for combo in combinations:
        times = get_all_times_from_combination(combo)
        all_times.extend(times)
    
    if not all_times:
        return 0.0
    
    start_times = [time_to_minutes(t.get("startTime", "")) for t in all_times if t.get("startTime")]
    end_times = [time_to_minutes(t.get("endTime", "")) for t in all_times if t.get("endTime")]
    
    if not start_times:
        return 0.0
    
    if preferred_start and preferred_end:
        pref_start_min = time_to_minutes(preferred_start)
        pref_end_min = time_to_minutes(preferred_end)
        pref_center = (pref_start_min + pref_end_min) / 2
        
        # Score based on how close times are to preferred center
        score = 0.0
        for start in start_times:
            distance = abs(start - pref_center)
            max_distance = (pref_end_min - pref_start_min) / 2
            if max_distance > 0:
                score += max(0, 1.0 - (distance / max_distance))
        return score / len(start_times) if start_times else 0.0
    else:
        # Calculate natural center of all times
        mean_start = sum(start_times) / len(start_times)
        mean_end = sum(end_times) / len(end_times) if end_times else mean_start
        center = (mean_start + mean_end) / 2
        
        # Score based on how close times are to the natural center
        score = 0.0
        total_spread = max(end_times) - min(start_times) if end_times and start_times else 1
        for start in start_times:
            distance = abs(start - center)
            if total_spread > 0:
                score += max(0, 1.0 - (distance / total_spread))
        return score / len(start_times) if start_times else 0.0


def find_valid_combinations(course_id: str) -> List[Dict]:
    """
    Find all valid lecture+section combinations for a course.
    Only pairs sections with their associated lectures.
    
    IMPORTANT: Sections are matched to lectures based on the UCSB API structure:
    - Sections in the same API response (same enroll code file) belong to that lecture
    - This is the authoritative source of truth - sections are structurally linked to their lecture
    - Section instructors may differ from lecture instructor (TAs teach sections), which is normal
    - The get_course_info() function verifies this structural relationship
    
    Returns list of combinations, each with lecture and optional section info.
    """
    course_info = get_course_info(course_id)
    if not course_info:
        return []
    
    lectures = course_info.get("lectureSections", [])
    all_sections = course_info.get("sections", [])
    
    combinations = []
    
    for lecture_idx, lecture in enumerate(lectures):
        lecture_times = lecture.get("times", [])
        lecture_enroll_code = lecture.get("enrollCode")
        
        # Get sections that belong to this lecture
        # These sections are guaranteed to belong to this lecture because they come from
        # the same API response (same enroll code file) - verified in get_course_info()
        lecture_sections = lecture.get("sections", [])
        
        if not lecture_sections:
            # No sections needed - just add lecture
            combinations.append({
                "lectureIndex": lecture_idx,
                "lecture": lecture,
                "sectionIndex": None,
                "section": None
            })
        else:
            # Check each section that belongs to this lecture
            for section in lecture_sections:
                section_times = section.get("times", [])
                
                # Find the index in the all_sections array for backward compatibility
                section_idx = None
                for idx, sec in enumerate(all_sections):
                    if sec.get("enrollCode") == section.get("enrollCode"):
                        section_idx = idx
                        break
                
                # Check if lecture and section conflict with each other
                conflicts = False
                if lecture_times and section_times:
                    conflicts = check_times_conflict(lecture_times, section_times)
                
                if not conflicts:
                    combinations.append({
                        "lectureIndex": lecture_idx,
                        "lecture": lecture,
                        "sectionIndex": section_idx,
                        "section": section
                    })
    
    return combinations


def generate_all_schedule_combinations(course_ids: List[str]) -> List[List[Dict]]:
    """
    Generate all valid schedule combinations across multiple courses.
    Returns list of schedules, where each schedule is a list of course combinations.
    """
    all_combinations_per_course = []
    
    for course_id in course_ids:
        combinations = find_valid_combinations(course_id)
        if not combinations:
            return []  # If any course has no valid combinations, return empty
        all_combinations_per_course.append(combinations)
    
    # Generate cartesian product of all combinations
    all_schedules = []
    for combo_product in product(*all_combinations_per_course):
        # Check if this combination has any internal conflicts
        schedule_times = []
        for combo in combo_product:
            if combo["lecture"] and combo["lecture"].get("times"):
                schedule_times.extend(combo["lecture"]["times"])
            if combo["section"] and combo["section"].get("times"):
                schedule_times.extend(combo["section"]["times"])
        
        # Check for conflicts within this schedule
        has_conflict = False
        for i, time1 in enumerate(schedule_times):
            for j, time2 in enumerate(schedule_times):
                if i < j and has_time_conflict(time1, time2):
                    has_conflict = True
                    break
            if has_conflict:
                break
        
        if not has_conflict:
            all_schedules.append(list(combo_product))
    
    return all_schedules


def score_schedule(combinations: List[Dict], preferences: Dict) -> float:
    """
    Score a schedule based on user preferences.
    Returns a score where higher = better.
    """
    if not combinations:
        return 0.0
    
    score = 100.0  # Start with base score
    
    # Preference: centered vs spread
    spread_preference = preferences.get("spreadPreference", "centered")  # "centered" or "spread"
    
    if spread_preference == "centered":
        center_score = calculate_schedule_center_score(combinations)
        score += center_score * 30.0  # Up to 30 points for centering
        spread = calculate_schedule_spread(combinations)
        score -= spread * 0.01  # Penalize large spreads
    else:  # spread
        spread = calculate_schedule_spread(combinations)
        score += min(spread * 0.05, 30.0)  # Reward spreading (up to 30 points)
    
    # Preference: preferred time window
    preferred_start = preferences.get("preferredStartTime")
    preferred_end = preferences.get("preferredEndTime")
    
    if preferred_start and preferred_end:
        center_score = calculate_schedule_center_score(combinations, preferred_start, preferred_end)
        score += center_score * 20.0  # Up to 20 points for preferred time
    
    # Preference: avoid early morning
    avoid_early = preferences.get("avoidEarlyMorning", False)
    if avoid_early:
        all_times = []
        for combo in combinations:
            all_times.extend(get_all_times_from_combination(combo))
        early_count = sum(1 for t in all_times 
                         if time_to_minutes(t.get("startTime", "")) < 540)  # Before 9 AM
        score -= early_count * 10.0  # Penalize early classes
    
    # Preference: avoid late evening
    avoid_late = preferences.get("avoidLateEvening", False)
    if avoid_late:
        all_times = []
        for combo in combinations:
            all_times.extend(get_all_times_from_combination(combo))
        late_count = sum(1 for t in all_times 
                        if time_to_minutes(t.get("startTime", "")) > 1020)  # After 5 PM
        score -= late_count * 10.0  # Penalize late classes
    
    # Preference: prioritize free days (minimize days with classes)
    prioritize_free_days = preferences.get("prioritizeFreeDays", False)
    if prioritize_free_days:
        days_with_classes = set()
        for combo in combinations:
            times = get_all_times_from_combination(combo)
            for time_info in times:
                days = time_info.get("days", "")
                for day in days:
                    if day in ['M', 'T', 'W', 'R', 'F']:
                        days_with_classes.add(day)
        
        # Reward fewer days with classes (more free days)
        num_days_with_classes = len(days_with_classes)
        free_days = 5 - num_days_with_classes
        score += free_days * 15.0  # Up to 75 points for having all days free (unlikely but rewarded)
    
    # Preference: minimize gaps between classes
    minimize_gaps = preferences.get("minimizeGaps", False)
    if minimize_gaps:
        # Group times by day and calculate gaps
        day_times = {'M': [], 'T': [], 'W': [], 'R': [], 'F': []}
        for combo in combinations:
            times = get_all_times_from_combination(combo)
            for time_info in times:
                days = time_info.get("days", "")
                start_time = time_to_minutes(time_info.get("startTime", ""))
                end_time = time_to_minutes(time_info.get("endTime", ""))
                if start_time and end_time:
                    for day in days:
                        if day in day_times:
                            day_times[day].append((start_time, end_time))
        
        # Calculate total gaps
        total_gap_minutes = 0
        for day, times_list in day_times.items():
            if len(times_list) > 1:
                # Sort by start time
                sorted_times = sorted(times_list, key=lambda x: x[0])
                for i in range(len(sorted_times) - 1):
                    gap = sorted_times[i + 1][0] - sorted_times[i][1]
                    if gap > 0:
                        total_gap_minutes += gap
        
        # Penalize large gaps (smaller gaps = better score)
        # Normalize: assume max gap could be ~8 hours = 480 minutes between classes
        if total_gap_minutes > 0:
            gap_penalty = min(total_gap_minutes / 10.0, 50.0)  # Max 50 point penalty
            score -= gap_penalty
        else:
            # No gaps = bonus
            score += 20.0
    
    # Preference: maximum classes per day
    max_classes_per_day = preferences.get("maxClassesPerDay")
    if max_classes_per_day:
        day_class_counts = {'M': 0, 'T': 0, 'W': 0, 'R': 0, 'F': 0}
        for combo in combinations:
            times = get_all_times_from_combination(combo)
            for time_info in times:
                days = time_info.get("days", "")
                for day in days:
                    if day in day_class_counts:
                        day_class_counts[day] += 1
        
        # Penalize days that exceed the limit
        for day, count in day_class_counts.items():
            if count > max_classes_per_day:
                excess = count - max_classes_per_day
                score -= excess * 25.0  # Heavy penalty for exceeding limit
    
    # Preference: preferred time of day
    preferred_time_of_day = preferences.get("preferredTimeOfDay")
    if preferred_time_of_day:
        all_times = []
        for combo in combinations:
            all_times.extend(get_all_times_from_combination(combo))
        
        if preferred_time_of_day == "morning":
            # Prefer classes before 12 PM (noon)
            morning_count = sum(1 for t in all_times 
                              if time_to_minutes(t.get("startTime", "")) < 720)  # Before 12 PM
            score += morning_count * 8.0
        elif preferred_time_of_day == "afternoon":
            # Prefer classes between 12 PM and 5 PM
            afternoon_count = 0
            for t in all_times:
                start_min = time_to_minutes(t.get("startTime", ""))
                if 720 <= start_min <= 1020:  # 12 PM to 5 PM
                    afternoon_count += 1
            score += afternoon_count * 8.0
        elif preferred_time_of_day == "evening":
            # Prefer classes after 5 PM
            evening_count = sum(1 for t in all_times 
                               if time_to_minutes(t.get("startTime", "")) > 1020)  # After 5 PM
            score += evening_count * 8.0
    
    return score


def optimize_schedules(course_ids: List[str], preferences: Dict, max_results: int = 10) -> List[Dict]:
    """
    Find optimal schedules for given courses based on preferences.
    Returns list of schedules sorted by score (best first).
    """
    if not course_ids:
        return []
    
    # Generate all valid combinations
    all_schedules = generate_all_schedule_combinations(course_ids)
    
    if not all_schedules:
        return []
    
    # Score each schedule
    scored_schedules = []
    for schedule in all_schedules:
        score = score_schedule(schedule, preferences)
        scored_schedules.append({
            "schedule": schedule,
            "score": score
        })
    
    # Sort by score (descending)
    scored_schedules.sort(key=lambda x: x["score"], reverse=True)
    
    # Return top results
    return scored_schedules[:max_results]


def format_schedule_result(scored_schedule: Dict, course_ids: List[str]) -> Dict:
    """
    Format a scored schedule result for API response.
    """
    schedule = scored_schedule["schedule"]
    result = {
        "score": scored_schedule["score"],
        "courses": []
    }
    
    for i, combo in enumerate(schedule):
        course_id = course_ids[i] if i < len(course_ids) else "Unknown"
        course_info = get_course_info(course_id)
        
        formatted_combo = {
            "courseId": course_id,
            "title": course_info.get("title", "") if course_info else "",
            "lecture": {
                "enrollCode": combo["lecture"].get("enrollCode"),
                "section": combo["lecture"].get("section"),
                "instructor": combo["lecture"].get("instructor", ""),
                "times": combo["lecture"].get("times", []),
                "enrolled": combo["lecture"].get("enrolled", 0),
                "maxEnroll": combo["lecture"].get("maxEnroll", 0)
            }
        }
        
        if combo["section"]:
            formatted_combo["section"] = {
                "enrollCode": combo["section"].get("enrollCode"),
                "section": combo["section"].get("section"),
                "instructor": combo["section"].get("instructor", ""),
                "times": combo["section"].get("times", []),
                "enrolled": combo["section"].get("enrolled", 0),
                "maxEnroll": combo["section"].get("maxEnroll", 0)
            }
        
        result["courses"].append(formatted_combo)
    
    return result
