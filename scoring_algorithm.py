# This program will sort courses that made it through the filtering process using the user's preferences/information.

# Each course will be assigned a score out of 100, and we will initially display the top ones according to how well they meet the user's criteria

# Idea: store user preferences in a dict and add keys to those dicts for the preferences the user has selected

# perhaps one of those keys will be the weights selected for each of the dicts, another dict

# write functions to calcualte score for each weight, then sum those all together to get a final score for each course

#filtering returns enroll codes, and then we get here

import requests
from datetime import datetime, timedelta
import json
import pandas as pd
import numpy as np



MY_API_KEY = input("Enter your API key: ")

headers = {
    'accept': 'text/plain',
    'ucsb-api-key': MY_API_KEY
}
date = "20261"
class_code = "03558" #Currently: W 2026 CH ST 1B
url = f"https://api.ucsb.edu/academics/curriculums/v3/classes/{date}/{class_code}?includeClassSections=true"

def getData(year, quarter, class_code):
   class_url = f"https://api.ucsb.edu/academics/curriculums/v3/classes/{date}/{class_code}?includeClassSections=true"
   response = requests.get(class_url, headers=headers)
   return response.json() if response.status_code == 200 else None

# put filtered grades from daily nexus into a data frame
grades_df = pd.read_csv('grades_filtered.csv')
#separates by department by taking a class name (ex ECE 10) and removing the class code (10)
grades_df['department'] = grades_df['course'].str.extract(r'^([A-Z\s]+)')[0].str.strip() 
grades_df['A_rate'] = grades_df['A'] / grades_df['nLetterStudents']

#calculates the mean and st dev for each department
dept_stats = grades_df.groupby('department')['A_rate'].agg(['mean', 'std']).reset_index() 

# User preferences (next step: get the input for this from the ui)
user_preferences = { 
   "ge": {
      "ge_priority" : True,
      "ge_area" : "ETH"
   },
   "time_preference" : {
      "start" : "10:30",
      "end" : "14:30"
   },
   "avoid_days": [],
   "preferred_units" : 5,
   "weights" : {
      "ge" : 30,
      "time" : 25,
      "day" : 15,
      "units" : 10,
      "grade_dist" : 20
   }
}

def ge_score(course, prefs):
   course_ges = course.get("generalEducation")
   

   if not prefs["ge"]["ge_priority"]:
      return 1.0
   
   if not course_ges:
      return 0.0
   
   for ge in course_ges:
    if prefs["ge"]["ge_area"] == ge.get("geCode"):
       return 1.0
    
   return 0.0

def time_score(course, prefs, format = "%H:%M"):
    course_start = datetime.strptime(course["classSections"][0]["timeLocations"][0]["beginTime"], format)
    earliest = datetime.strptime(prefs["time_preference"]["start"], format)
    latest = datetime.strptime(prefs["time_preference"]["end"], format)

    if course_start < earliest or course_start > latest:
        return 0.0
    
    mid = earliest + (latest - earliest) / 2
    score = 1.0 - abs(course_start - mid) / ((latest - earliest) / 2) 
    return max(0.0, min(1.0, score))

def day_score(course, prefs):
   days = prefs["avoid_days"]
   for day in days:
    if day in course["classSections"][0]["timeLocations"][0]["days"]:
      return 0.0
   return 1.0

def units_score(course, prefs):
    target = prefs["preferred_units"]
    score = 1.0 - abs(course["unitsFixed"] - target) / target
    return max(0.0, score)

def grade_dist_score(course, prefs):
    
    #Calculate normalized grade distribution score (0-1) for a course.
    #Normalizes by department to account for the mean/std dev of each
    
    course_id = course.get('courseId', '').strip()
    
    if not course_id:
        return 0.5
    
    # Get instructor names
    instructors = []
    for section in course.get('classSections', []):
        for instr in section.get('instructors', []):
            instr_name = instr.get('instructor', '').strip()
            if instr_name:
                instructors.append(instr_name)
    
    # Look up course in grades dataframe
    course_grades = grades_df[grades_df['course'].str.strip() == course_id]
    
    if course_grades.empty:
        return 0.5
    
    # Filter by instructor if available
    if instructors:
        instructor_grades = course_grades[course_grades['instructor'].isin(instructors)]
        if not instructor_grades.empty:
            course_grades = instructor_grades
    
    # Calculate average A rate
    avg_a_rate = course_grades['A_rate'].mean()
    department = course_grades.iloc[0]['department']
    
    # Get department stats
    dept_info = dept_stats[dept_stats['department'] == department]
    
    if dept_info.empty:
        return 0.5
    
    dept_mean = dept_info.iloc[0]['mean']
    dept_std = dept_info.iloc[0]['std']
    
    # Calculate z-score
    if dept_std == 0 or pd.isna(dept_std):
        z_score = 0
    else:
        z_score = (avg_a_rate - dept_mean) / dept_std
    
    # Convert to normalized score bewteen 0 and 1 (sigmoid function)
    normalized_score = 1 / (1 + np.exp(-z_score))
    
    return normalized_score

def score_course(course, prefs):
   weights = prefs["weights"]

   ge_weighted_score = ge_score(course, prefs) * weights["ge"]
   time_weighted_score = time_score(course, prefs) * weights["time"]
   day_weighted_score = day_score(course, prefs) * weights["day"]
   units_weighted_score = units_score(course, prefs) * weights["units"]
   grade_weighted_score = grade_dist_score(course, prefs) * weights["grade_dist"]

   print(f"GE weighted score: {ge_weighted_score}")
   print(f"Time weighted score: {time_weighted_score:.2f}")
   print(f"Day weighted score: {day_weighted_score}")
   print(f"Units weighted score: {units_weighted_score:.2f}")
   print(f"Grade dist weighted score: {grade_weighted_score:.2f}")

   total = (
       ge_weighted_score +
       time_weighted_score +
       units_weighted_score +
       day_weighted_score +
       grade_weighted_score
   )

   return round(total)

def rank_courses(courses, prefs):
    for course in courses:
        course["score"] = score_course(course, prefs)
    
    sorted_courses = sorted(courses, key = lambda course: course["score"], reverse = True)
    return sorted_courses
   
class1 = getData(date, 1, class_code)
if class1:
    print(f"\n{class1.get('title')} Score: {score_course(class1, user_preferences)}/100")


      
   
    




















