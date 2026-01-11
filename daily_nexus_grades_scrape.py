#This program will scrape data from the course_grades.csv file used in Daily Nexus Grades
#it will return the portion of the data set from 2021 onwards, and with only the revelant columns:
#course, instructor, quarter, year, # of As, # of students in the class

import pandas as pd

# Load the file with only the columns you need
df = pd.read_csv('courseGrades.csv', usecols=['course', 'instructor', 'quarter', 'year', 'A', 'nLetterStudents'])

# Filter for last 5 years (2021 onwards)
df_filtered = df[df['year'] >= 2021]

# View the data
print(df_filtered.head())
print(f"\nTotal records from 2020+: {len(df_filtered)}")

# Analyze A distributions by instructor
instructor_stats = df_filtered.groupby('instructor').agg({
    'A': ['mean', 'sum'],  # Average A rate and total A's
    'course': 'count'  # Number of classes taught
}).round(3)

instructor_stats.columns = ['avg_A_rate', 'total_As', 'num_classes']
print("\nTop instructors by A rate:")
print(instructor_stats.sort_values('avg_A_rate', ascending=False).head(10))