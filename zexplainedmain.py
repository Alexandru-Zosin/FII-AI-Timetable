import random
import json
import time as t
import copy
import cProfile
from flask import Flask, render_template, url_for

########################################################################
# The code below attempts to build an academic timetable that satisfies
# a set of constraints (restrictions). The timetable must ensure:
#  1) Mandatory subjects are assigned to each group.
#  2) No overlapping classes for the same group at the same time.
#  3) A teacher does not teach two classes at the same time.
#  4) A room cannot have two classes at the same time.
#  5) A course must be taught in a room that supports courses.
#  6) Seminars must be in rooms that do NOT support courses.
#  7) A professor cannot exceed max teaching hours.
#  8) Courses must be scheduled before seminars for the same subject & group.
#
# Because the code is partially in Romanian and partially in English,
# an English-only version has been created (eng_main.py).
# Nevertheless, we keep main.py for those who wrote it originally.
########################################################################

restrictions = []  # These restrictions can be checked after the entire timetable is built
duringConstructionRestrictions = []  # Restricții verificate (optional) in the process of building the timetable

# Data file names. We expect JSON files with these names in the ./data directory.
fileNames = ['grupe', 'materii', 'profesori', 'sali', 'timp', 'extraRestrictions']
loadedData = {}

# Load data from JSON files in the 'data' directory
for fileName in fileNames:
    with open(f'./data/{fileName}.json', 'r') as file:
        readData = json.load(file)
        loadedData[fileName] = readData

# Dictionary lookups for quick access by 'cod' fields
group_codes = {group['cod']: group for group in loadedData['grupe']}
sala_codes = {sala['cod']: sala for sala in loadedData['sali']}
profesor_codes = {profesor['cod']: profesor for profesor in loadedData['profesori']}
materie_codes = {materie['cod']: materie for materie in loadedData['materii']}
time_codes = {time['cod']: time for time in loadedData['timp']}

# Initialize the data structures needed for building the timetable
bestTimeTable = None             # Stores the best timetable found
bestTimeTableScore = 0          # Stores the "score" (not fully used in this example)
currentTimetable = {}           # currentTimetable[profesorIndex][timeIndex] = (grupa, sala, materie, class_type)
profesor_hours = {}             # Tracks how many hours each professor is assigned
group_schedule = {}             # Tracks which timeslots each group is using
sala_schedule = {}              # Tracks which timeslots each room is using

########################################################################
# Restriction functions (the "fX" definitions) appear below.
# Some are commented out or partially used. They are meant to check
# various constraints after or during the timetable construction.
########################################################################

def f1(currentTimetable):
    """
    Restriction f1:
    - No group has overlapping classes.
    - Also ensures no two classes in the same classroom at once.
    In the current code, we are returning True because
    we handle these constraints during the assignment steps.
    """
    return True  # Handled during assignment

# Identify which subjects are mandatory or optional
required_subjects = [subject['cod'] for subject in loadedData['materii'] if subject['este_optionala'] == 0]
required_subjects_set = set(required_subjects)
optional_subjects = [subject['cod'] for subject in loadedData['materii'] if subject['este_optionala'] == 1]
optional_subjects_set = set(optional_subjects)

def f2(currentTimetable):
    """
    Restriction f2:
    - Each group has assigned all mandatory (non-optional) subjects.
    - We collect all subjects assigned to each group in the current timetable
      and check if the mandatory subjects are all covered.
    """
    global required_subjects_set
    group_subjects = {}

    # Accumulate assigned subjects for each group
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
            if grupa not in group_subjects:
                group_subjects[grupa] = set()
            if materie in required_subjects:
                group_subjects[grupa].add(materie)

    # Now check if all required subjects are present
    for grupa in group_codes:
        if grupa not in group_subjects:
            assigned_subjects = set()
        else:
            assigned_subjects = group_subjects[grupa]
        if len(required_subjects_set) != len(assigned_subjects):
            return False
    return True

def f3(currentTimetable):
    """
    Restriction f3:
    - A group has a particular subject only once. This typically means:
      - For a group X and subject Y, you cannot schedule multiple identical "courses" or "seminars".
        The code checks if the group is a main group (length of group_nume == 1 => course)
        or a sub-group (length > 1 => seminar).
      - This is somewhat simplified here: if a group tries to get the same subject
        multiple times, it returns False.
    """
    group_subject_course = {}
    group_subject_seminar = {}

    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie, class_type= currentTimetable[profesorIndex][timeIndex]
            grupa_nume = group_codes[grupa]['nume']
            is_course = len(grupa_nume) == 1

            key = (grupa, materie)
            # If it's a course group (length == 1) check if we already have that subject
            if is_course:
                if key in group_subject_course:
                    return False
                group_subject_course[key] = True
            else:
                # It's a seminar group
                if key in group_subject_seminar:
                    return False
                group_subject_seminar[key] = True

    return True

def f4(currentTimetable):
    """
    Restriction f4:
    - Courses can only be held in classrooms that allow courses (curs_posibil == 1).
    - Seminars must be in classrooms that do NOT allow courses (curs_posibil == 0).
    """
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
            sala_info = sala_codes[sala]
            grupa_nume = group_codes[grupa]['nume']
            is_course = len(grupa_nume) == 1

            if is_course and sala_info['curs_posibil'] != 1:
                return False
            if not is_course and sala_info['curs_posibil'] != 0:
                return False
    return True

def f5(currentTimetable):
    """
    Restriction f5:
    - The course must be scheduled before the seminar for the same subject & group.
      Concretely, if the subject is the same, the time slot for the course
      must be strictly less (earlier) than the time slot for the seminar.
    """
    subject_course_times = {}
    subject_seminar_times = {}

    # Collect the earliest timeIndex for the course and seminar for each subject & group
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
            grupa_nume = group_codes[grupa]['nume']
            is_course = len(grupa_nume) == 1
            key = materie

            if is_course:
                if key not in subject_course_times:
                    subject_course_times[key] = []
                subject_course_times[key].append(timeIndex)
            else:
                if key not in subject_seminar_times:
                    subject_seminar_times[key] = []
                subject_seminar_times[key].append(timeIndex)

    # For each subject that has seminars, check if there's a valid (earlier) course time
    for key in subject_seminar_times:
        if key in subject_course_times:
            min_course_time = min(subject_course_times[key])
            min_seminar_time = min(subject_seminar_times[key])
            # If the earliest seminar time is less or equal to the course time => violation
            if min_seminar_time <= min_course_time:
                return False
        else:
            # If we have a seminar but no course found, it's also a violation
            return False

    return True

def f6(currentTimetable):
    """
    Restriction f6:
    - A teacher can only teach subjects assigned to him/her.
    - If a teacher is assigned a subject not in their 'materiiPredate', return False.
    """
    for profesorIndex in currentTimetable:
        profesor = profesor_codes[profesorIndex]
        subjects_assigned = set(profesor['materiiPredate'])
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
            if materie not in subjects_assigned:
                return False
    return True

def f7(currentTimetable):
    """
    Restriction f7:
    - The course is only assigned to a professor who can teach at a course (poatePredaCurs == 1).
    - If the group name length is 1 (which means it's a main group => course), then the professor
      must have 'poatePredaCurs' set to 1.
    """
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
            profesor = profesor_codes[profesorIndex]
            if len(group_codes[grupa]['nume']) == 1 and profesor['poatePredaCurs'] == 0:
                return False
    return True

# (Some restrictions are appended in the code below, if needed. Currently not used.)
# restrictions.append(f1)
# restrictions.append(f2)
# restrictions.append(f7)
# restrictions.append(f3)
# restrictions.append(f4)
# restrictions.append(f5)
# restrictions.append(f6)

# duringConstructionRestrictions.append(f6)
# duringConstructionRestrictions.append(f4)
# duringConstructionRestrictions.append(f3)

########################################################################
# Helper functions to check the timetable validity globally or during assignment
########################################################################

def isTimeTableValid():
    """
    Check if the current timetable satisfies all restrictions in the 'restrictions' list
    (after the entire timetable is built).
    """
    for restriction in restrictions:
        if not restriction(currentTimetable):
            return False
    return True

def checkRequirementsDuringConstruction():
    """
    Checks partial restrictions while building the timetable, if used.
    Currently not heavily used in this code, returns True if partial checks pass.
    """
    for dTypeRestriction in duringConstructionRestrictions:
        if not dTypeRestriction(currentTimetable):
            return False
    return True

def calculateTimeTableScoreBasedOnSoftRestrictions():
    """
    Stub function for adding a "soft" score to the timetable.
    Currently always returns 1.
    """
    return 1

########################################################################
# Functions to add/remove classes in the timetable
########################################################################

def addToTimeTable(profesorIndex, timeIndex, grupa, sala, materie, class_type):
    """
    Attempts to add an assignment (profesorIndex, timeIndex, grupa, sala, materie, class_type)
    to currentTimetable. It returns True if successful, False otherwise.
    - We check if the group or the sala is already busy at timeIndex.
    - We also increment the teacher's hours if added.
    """
    if profesorIndex not in currentTimetable:
        currentTimetable[profesorIndex] = {}

    # Check if group already has a class in that timeslot
    if grupa not in group_schedule:
        group_schedule[grupa] = set()
    if timeIndex in group_schedule[grupa]:
        return False

    # Check if room (sala) is already occupied at that timeslot
    if sala not in sala_schedule:
        sala_schedule[sala] = set()
    if timeIndex in sala_schedule[sala]:
        return False

    # If we reach here, we can safely add it
    currentTimetable[profesorIndex][timeIndex] = (grupa, sala, materie, class_type)

    # Increment the hours for this professor
    profesor_hours[profesorIndex] += 1

    # Mark the group and sala as busy at this timeslot
    group_schedule[grupa].add(timeIndex)
    sala_schedule[sala].add(timeIndex)
    return True

def removeFromTimeTable(profesorIndex, timeIndex):
    """
    Removes an assignment (profesorIndex, timeIndex) from the timetable
    and updates the relevant data structures.
    """
    if profesorIndex in currentTimetable and timeIndex in currentTimetable[profesorIndex]:
        grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
        del currentTimetable[profesorIndex][timeIndex]
        profesor_hours[profesorIndex] -= 1
        group_schedule[grupa].remove(timeIndex)
        sala_schedule[sala].remove(timeIndex)

########################################################################
# Build a list of all classes (course/seminar for mandatory and optional subjects)
# that must be scheduled.
########################################################################

class_list = []

for materie in loadedData['materii']:
    if materie['este_optionala'] == 0:
        # Mandatory subject
        for group in loadedData['grupe']:
            group_nume = group['nume']
            if len(group_nume) == 1:
                # main group => course
                class_list.append({
                    'type': 'course',
                    'materie': materie['cod'],
                    'grupa': group['cod']
                })
            else:
                # sub-group => seminar
                class_list.append({
                    'type': 'seminar',
                    'materie': materie['cod'],
                    'grupa': group['cod']
                })
    else:
        # Optional subject
        main_groups = [group for group in loadedData['grupe'] if len(group['nume']) == 1]
        for group in main_groups:
            # Add both a 'course' and 'seminar' for each main group
            class_list.append({
                'type': 'course',
                'materie': materie['cod'],
                'grupa': group['cod']
            })
        for group in main_groups:
            class_list.append({
                'type': 'seminar',
                'materie': materie['cod'],
                'grupa': group['cod']
            })

# bar_plot_values is not used heavily, but might store iteration data for analytics
bar_plot_values = []

########################################################################
# The backtracking function tries to assign all classes in class_list.
########################################################################
def backtracking(class_index):
    global bestTimeTable, bestTimeTableScore, bar_plot_values

    # Base case: if we've assigned all classes, check validity and store the solution
    if class_index == len(class_list):
        if isTimeTableValid():
            bestTimeTable = copy.deepcopy(currentTimetable)
            return 1
        return 0

    # Get the class to be scheduled
    cls = class_list[class_index]
    materie = cls['materie']
    grupa = cls['grupa']
    class_type = cls['type']  # 'course' or 'seminar'

    # Find all professors who can teach this 'materie'
    possible_professors = []
    for profesor in loadedData['profesori']:
        if materie in profesor['materiiPredate']:
            profesorIndex = profesor['cod']
            possible_professors.append(profesorIndex)

    # Try each professor
    for profesorIndex in possible_professors:
        # If it's a course, the professor must be able to teach a course
        if class_type == 'course' and profesor_codes[profesorIndex]['poatePredaCurs'] == 0:
            continue

        # Check if the professor doesn't exceed maximum hours
        nrMaximOre = profesor_codes[profesorIndex]['nrMaximOre']
        if profesorIndex not in profesor_hours:
            profesor_hours[profesorIndex] = 0
        if profesor_hours[profesorIndex] >= nrMaximOre:
            continue

        # Now iterate over all possible time slots
        for time in loadedData['timp']:
            timeIndex = time['cod']

            # If the group is already busy at this timeslot, skip it
            if timeIndex in group_schedule.get(grupa, {}):
                continue

            # If the professor is already busy at this timeslot, skip it
            if timeIndex in currentTimetable.get(profesorIndex, {}):
                continue

            # Iterate over all possible classrooms for this timeslot
            for sala in loadedData['sali']:
                salaIndex = sala['cod']
                is_course = (class_type == 'course')

                # If it's a course but the room does not allow courses, skip
                if is_course and sala['curs_posibil'] != 1:
                    continue

                # If the timeslot is not possible for that sala, skip
                if timeIndex not in sala['timp_posibil']:
                    continue

                # Attempt to add to timetable
                if addToTimeTable(profesorIndex, timeIndex, grupa, salaIndex, materie, class_type):
                    # Recursively assign next class
                    returnValue = backtracking(class_index + 1)
                    if returnValue == 1:
                        return 1
                    # If assignment fails, remove it and try another possibility
                    removeFromTimeTable(profesorIndex, timeIndex)

# Start the backtracking from the first class
backtracking(0)

########################################################################
# After the timetable is built (bestTimeTable found), we transform it
# into a structured format (timetable_data) that the Flask app can display.
########################################################################
def transform_data(bestTimeTable, profesor_codes, time_codes, sala_codes, materie_codes, group_codes):
    """
    This function converts the final bestTimeTable into a data structure
    suitable for rendering on an HTML page.
    The returned timetable_data is structured so that:
       timetable_data[group][zi] = list of classes for that day (zi).
    Each class has keys: Interval, Disciplina, Profesor, Sala, Tip
    """
    timetable_data = {}

    for profesorIndex, schedule in bestTimeTable.items():
        profesor = profesor_codes[profesorIndex]["numeProfesor"]

        for timeIndex, details in schedule.items():
            grupa, sala, materie, class_type = details
            zi = time_codes[timeIndex]["zi"]
            ora = time_codes[timeIndex]["ora"]

            # Construct a time interval string (e.g. "08-10")
            interval = f"{ora[:2]}-{str(int(ora[:2]) + 2).zfill(2)}"

            row = {
                "Interval": interval,
                "Disciplina": materie_codes[materie]["nume"],
                "Profesor": profesor,
                "Sala": sala_codes[sala]["nume"],
                "Tip": class_type
            }

            # Build the nested dictionary structure
            timetable_data.setdefault(grupa, {}).setdefault(zi, []).append(row)

    # Sort the entries for each day by time interval
    for grupa in timetable_data:
        for zi in timetable_data[grupa]:
            timetable_data[grupa][zi] = sorted(timetable_data[grupa][zi], key=lambda x: x["Interval"])

    return timetable_data

# Convert our bestTimeTable into a displayable structure
timetable_data = transform_data(bestTimeTable, profesor_codes, time_codes, sala_codes, materie_codes, group_codes)

########################################################################
# Set up a simple Flask web server with two routes:
#  1) '/' -> shows a list of groups
#  2) '/timetable/<int:group>' -> shows the timetable for that group
########################################################################
app = Flask(__name__)

# Main page: display the list of group codes
@app.route('/')
def index():
    groups = timetable_data.keys()
    return render_template('index.html', groups=groups)

# Page to display the timetable for an individual group
@app.route('/timetable/<int:group>')
def timetable(group):
    if group not in timetable_data:
        return "Orarul pentru această grupă nu este disponibil.", 404
    
    data = timetable_data[group]
    return render_template('timetable.html', group=group, timetable_data=data)

# Run the Flask app
app.run(debug=True)
