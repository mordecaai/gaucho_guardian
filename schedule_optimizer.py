"""
Schedule Optimizer - Finds optimal lecture/section combinations for selected courses
"""
from typing import List, Dict, Optional, Tuple
from course_service import get_course_info, has_time_conflict, check_times_conflict
from itertools import product
import heapq
from functools import lru_cache


# Cache for time conversions to avoid repeated parsing
_time_cache: Dict[str, int] = {}

def time_to_minutes(time_str: str) -> int:
    """Convert time string (HH:MM) to minutes since midnight (memoized)"""
    if not time_str:
        return 0
    if time_str in _time_cache:
        return _time_cache[time_str]
    parts = time_str.split(':')
    if len(parts) != 2:
        _time_cache[time_str] = 0
        return 0
    try:
        result = int(parts[0]) * 60 + int(parts[1])
        _time_cache[time_str] = result
        return result
    except (ValueError, TypeError):
        _time_cache[time_str] = 0
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


def check_schedule_conflicts_fast(schedule_times: List[Dict]) -> bool:
    """
    Optimized conflict checking using day-based grouping.
    Returns True if there are conflicts, False otherwise.
    
    Groups times by day first, then checks for overlaps within each day.
    This is much faster than checking all pairs across all days.
    """
    if len(schedule_times) < 2:
        return False
    
    # Group times by day for faster conflict checking
    day_groups: Dict[str, List[Tuple[int, int]]] = {}
    
    for time_info in schedule_times:
        days = time_info.get("days", "").replace(" ", "")
        start_time = time_to_minutes(time_info.get("startTime", ""))
        end_time = time_to_minutes(time_info.get("endTime", ""))
        
        if not start_time or not end_time:
            continue
        
        for day in days:
            if day in ['M', 'T', 'W', 'R', 'F']:
                if day not in day_groups:
                    day_groups[day] = []
                day_groups[day].append((start_time, end_time))
    
    # Check conflicts within each day
    # For sorted intervals, checking adjacent pairs is sufficient and faster
    for day, intervals in day_groups.items():
        if len(intervals) < 2:
            continue
        # Sort by start time
        intervals.sort(key=lambda x: x[0])
        # Check adjacent intervals for overlap (sufficient for sorted intervals)
        for i in range(len(intervals) - 1):
            # Check if intervals overlap: start1 < end2 and end1 > start2
            # For sorted intervals, if i and i+1 don't overlap, i won't overlap with any j > i+1
            if intervals[i][0] < intervals[i + 1][1] and intervals[i][1] > intervals[i + 1][0]:
                return True
    
    return False


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


def generate_all_schedule_combinations(course_ids: List[str], max_results: Optional[int] = None) -> List[List[Dict]]:
    """
    Generate all valid schedule combinations across multiple courses.
    Returns list of schedules, where each schedule is a list of course combinations.
    
    If max_results is provided, stops early once we have enough valid schedules.
    """
    all_combinations_per_course = []
    
    # Pre-extract times for each combination to avoid repeated work
    combinations_with_times = []
    for course_id in course_ids:
        combinations = find_valid_combinations(course_id)
        if not combinations:
            return []  # If any course has no valid combinations, return empty
        
        # Pre-extract times for each combination
        combo_with_times = []
        for combo in combinations:
            times = get_all_times_from_combination(combo)
            combo_with_times.append((combo, times))
        combinations_with_times.append(combo_with_times)
        all_combinations_per_course.append(combinations)
    
    # Generate cartesian product of all combinations
    all_schedules = []
    count = 0
    
    for combo_product in product(*all_combinations_per_course):
        # Get pre-extracted times for this combination
        schedule_times = []
        for i, combo in enumerate(combo_product):
            # Find the corresponding times from our pre-extracted list
            combo_idx = all_combinations_per_course[i].index(combo)
            times = combinations_with_times[i][combo_idx][1]
            schedule_times.extend(times)
        
        # Use optimized conflict checking
        if not check_schedule_conflicts_fast(schedule_times):
            all_schedules.append(list(combo_product))
            count += 1
            # Early termination if we have enough results
            if max_results and count >= max_results:
                break
    
    return all_schedules


def score_schedule(combinations: List[Dict], preferences: Dict, pre_extracted_times: Optional[List[Dict]] = None) -> float:
    """
    Score a schedule based on user preferences.
    Returns a score where higher = better.
    
    If pre_extracted_times is provided, uses that instead of extracting times again.
    """
    if not combinations:
        return 0.0
    
    # Use pre-extracted times if available, otherwise extract them
    if pre_extracted_times is None:
        all_times = []
        for combo in combinations:
            all_times.extend(get_all_times_from_combination(combo))
    else:
        all_times = pre_extracted_times
    
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
        early_count = sum(1 for t in all_times 
                         if time_to_minutes(t.get("startTime", "")) < 540)  # Before 9 AM
        score -= early_count * 10.0  # Penalize early classes
    
    # Preference: avoid late evening
    avoid_late = preferences.get("avoidLateEvening", False)
    if avoid_late:
        late_count = sum(1 for t in all_times 
                        if time_to_minutes(t.get("startTime", "")) > 1020)  # After 5 PM
        score -= late_count * 10.0  # Penalize late classes
    
    # Preference: prioritize free days (minimize days with classes)
    prioritize_free_days = preferences.get("prioritizeFreeDays", False)
    if prioritize_free_days:
        days_with_classes = set()
        for time_info in all_times:
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
        for time_info in all_times:
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
        for time_info in all_times:
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
    
    Uses a heap-based approach to keep only the top N schedules, avoiding
    scoring all schedules if we have many combinations.
    """
    if not course_ids:
        return []
    
    # Pre-extract combinations and their times
    all_combinations_per_course = []
    combinations_with_times = []
    
    for course_id in course_ids:
        combinations = find_valid_combinations(course_id)
        if not combinations:
            return []  # If any course has no valid combinations, return empty
        
        # Pre-extract times for each combination
        combo_with_times = []
        for combo in combinations:
            times = get_all_times_from_combination(combo)
            combo_with_times.append((combo, times))
        combinations_with_times.append(combo_with_times)
        all_combinations_per_course.append(combinations)
    
    # Use a min-heap to keep only the top max_results schedules
    # We'll use negative scores since heapq is a min-heap
    heap = []
    
    # Generate combinations and score on-the-fly
    # Create mappings from combo to index using unique identifiers (enrollCode)
    combo_indices = []
    for i, combos in enumerate(all_combinations_per_course):
        combo_to_idx = {}
        for idx, combo in enumerate(combos):
            # Use lecture enrollCode as unique identifier
            lecture_code = combo.get("lecture", {}).get("enrollCode")
            section_code = combo.get("section", {}).get("enrollCode") if combo.get("section") else None
            key = (lecture_code, section_code)
            combo_to_idx[key] = idx
        combo_indices.append(combo_to_idx)
    
    count_processed = 0
    for combo_product in product(*all_combinations_per_course):
        # Get pre-extracted times for this combination
        schedule_times = []
        for i, combo in enumerate(combo_product):
            # Use enrollCode for fast lookup
            lecture_code = combo.get("lecture", {}).get("enrollCode")
            section_code = combo.get("section", {}).get("enrollCode") if combo.get("section") else None
            key = (lecture_code, section_code)
            combo_idx = combo_indices[i].get(key)
            if combo_idx is not None:
                times = combinations_with_times[i][combo_idx][1]
                schedule_times.extend(times)
        
        # Check for conflicts first (fast check)
        if check_schedule_conflicts_fast(schedule_times):
            continue
        
        # Score the schedule using pre-extracted times
        score = score_schedule(list(combo_product), preferences, schedule_times)
        
        count_processed += 1
        
        # Add to heap (using negative score for min-heap behavior - we want max scores)
        # Use count_processed as tiebreaker to avoid dict comparison errors
        if len(heap) < max_results:
            heapq.heappush(heap, (-score, count_processed, list(combo_product), schedule_times))
        else:
            # If heap is full, only add if this score is better than the worst
            # Compare negative scores (smaller negative = larger positive score)
            if -score < heap[0][0]:
                heapq.heapreplace(heap, (-score, count_processed, list(combo_product), schedule_times))
    
    if not heap:
        return []
    
    # Extract and sort results (best first)
    scored_schedules = []
    while heap:
        neg_score, _, schedule, _ = heapq.heappop(heap)
        score = -neg_score  # Convert back to positive
        scored_schedules.append({
            "schedule": schedule,
            "score": score
        })
    
    # Sort by score descending (best first)
    scored_schedules.sort(key=lambda x: x["score"], reverse=True)
    
    return scored_schedules


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
            "units": course_info.get("units", 0) if course_info else 0,
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
