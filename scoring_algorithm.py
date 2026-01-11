# This program will sort courses that made it through the filtering process using the user's preferences/information.

# Each course will be assigned a score out of 100, and we will initially display the top ones according to how well they meet the user's criteria

# Idea: store user preferences in a dict and add keys to those dicts for the preferences the user has selected

# perhaps one of those keys will be the weights selected for each of the dicts, another dict

# write functions to calcualte score for each weight, then sum those all together to get a final score for each course

#filtering returns enroll codes, and then we get here
import requests
from datetime import datetime, timedelta

MY_API_KEY = input("Enter your API key: ")

headers = {
    'accept': 'text/plain',
    'ucsb-api-key': MY_API_KEY
}
date = "20261"
class_code = "10736"
url = f"https://api.ucsb.edu/academics/curriculums/v3/classes/{date}/{class_code}?includeClassSections=true"


def isValidCode(year, quarter, class_code):
  response = requests.get(url, headers=headers)
  # Checking for sucessful request
  if response.status_code == 200:
      data = response.json()
      if(data): #check if data exists for pulling correct codes
        print(data.get("title")) 
        return True
        
      else:
        return False

#returns the data for a class as a json file, given its class code
def getData(year, quarter, class_code):
   class_url = f"https://api.ucsb.edu/academics/curriculums/v3/classes/{date}/{class_code}?includeClassSections=true"
   response = requests.get(class_url, headers=headers)
   return response.json() if response.status_code == 200 else None

class1 = getData(date, 1, class_code)

#these preferences will obviously change
user_preferences = { 
   "ge": {
      "ge_priority" : True,
      "ge_area" : "ETH"
   },

   "time_preference" : { #note: should have already accounted for courses that created a scheduling conflict during the filtering
      "start" : "09:00",
      "end" : "11:00" #3pm
   },

   "avoid_days": [], #can contain M, T, W, R, F

   "preferred_units" : 4,

   "weights" : {
      "ge" : 30,
      "time" : 25,
      "day" : 15,
      "units" : 10,
      "other" : 20 #change this later
   }

}

def ge_score(course, prefs):
   course_ges = course.get("generalEducation")
   
   if not course_ges:
      return 0.0
   
   if not prefs["ge"]["ge_priority"]:
      return 0.5 #neutral score
   
   for ge in course_ges:
    if prefs["ge"]["ge_area"] == ge.get("geCode"):
       return 1.0
    
    return 0.0

def time_score(course, prefs, format = "%H:%M"):
    #times are given in HH:MM format
    course_start = datetime.strptime(course["classSections"][0]["timeLocations"][0]["beginTime"], format)
    earliest = datetime.strptime(prefs["time_preference"]["start"], format)
    latest = datetime.strptime(prefs["time_preference"]["end"], format)

    if course_start < earliest or course_start > latest: #not in preferred window
        return 0.0
    
    mid = earliest + (latest - earliest) / 2

    #normalizes score between 0 and 1, where a time centered right between earliest and latest gets a score of 1
    score = 1.0 - abs(course_start - mid)/ ((latest - earliest)/2) 
    return max(0.0, min(1.0, score)) #gets rid of minor inconsistencies (negatives and values greater than 1)

def day_score(course, prefs):
   days = prefs["avoid_days"]
   for day in days:
    if(day in course["classSections"][0]["timeLocations"][0]["days"]):
      return 0.0
   
   return 1.0


def units_score(course, prefs):
    target = prefs["preferred_units"]
    score = 1.0 - abs(course["unitsFixed"] - target) / target
    return max(0.0,score)

    #percentage of A's
    #RMP instructor name + rating 

def score_course(course, prefs):
   weights = prefs["weights"]

   total = (
    ge_score(course, prefs)    * weights["ge"] +
        time_score(course, prefs)  * weights["time"] +
        units_score(course, prefs) * weights["units"]
   )

   return round(total)

courses = [] #this will hold all the courses to rank

def rank_courses(courses, prefs):
    for course in courses:
        course["score"] = score_course(course, prefs)
    
    sorted_courses = sorted(courses, key = lambda course: course["score"], reverse = True)
    return sorted_courses

print(f"{class1.get('title')} Score: {score_course(class1, user_preferences)}")
   

      
   
    




















