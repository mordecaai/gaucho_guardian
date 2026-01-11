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

#add the sorted data into a new csv file
df_filtered.to_csv('grades_filtered.csv', index=False)

print(f"Filtered {len(df_filtered)} records and saved to grades_filtered.csv")