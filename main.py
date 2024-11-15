import json
import time as t
import copy
restrictions = []
fileNames = ['grupe', 'materii', 'profesori', 'sali', 'timp', 'extraRestrictions']
loadedData = {}
# loading the data that we have
for fileName in fileNames:
    with open(f'./data/{fileName}.json', 'r') as file:
        readData = json.load(file)
        loadedData[fileName] = readData

group_codes = {group['cod']: group for group in loadedData['grupe']}
sala_codes = {sala['cod']: sala for sala in loadedData['sali']}
profesor_codes = {profesor['cod']: profesor for profesor in loadedData['profesori']}
materie_codes = {materie['cod']: materie for materie in loadedData['materii']}
time_codes = {time['cod']: time for time in loadedData['timp']}

# Initialize variables
bestTimeTable = None
bestTimeTableScore = 0
currentTimetable = {}  # currentTimetable[profesorIndex][timeIndex] = (grupa, sala, materie)
profesor_hours = {}
group_schedule = {}
sala_schedule = {}

# Define the restriction functions
def f1(currentTimetable):
    # Any group does not have overlapping classes
    # Any overlapping classes are in different classrooms
    return True  # Handled during assignment

def f2(currentTimetable):
    # Each group has assigned all mandatory subjects for their year
    group_subjects = {}
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie = currentTimetable[profesorIndex][timeIndex]
            if grupa not in group_subjects:
                group_subjects[grupa] = set()
            group_subjects[grupa].add(materie)
    for grupa in group_codes:
        grupa_info = group_codes[grupa]
        grupa_an = grupa_info['an']
        required_subjects = [subject['cod'] for subject in loadedData['materii']
                             if subject['este_optionala'] == 0 and subject['an'] == grupa_an]
        required_subjects_set = set(required_subjects)
        if grupa not in group_subjects:
            assigned_subjects = set()
        else:
            assigned_subjects = group_subjects[grupa]
        if not required_subjects_set.issubset(assigned_subjects):
            return False
    return True

def f3(currentTimetable):
    # A group has classes for a subject only once (max one course, max one seminar)
    group_subject_course = {}
    group_subject_seminar = {}
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie = currentTimetable[profesorIndex][timeIndex]
            grupa_nume = group_codes[grupa]['nume']
            is_course = len(grupa_nume) == 1
            key = (grupa, materie)
            if is_course:
                if key in group_subject_course:
                    return False
                group_subject_course[key] = True
            else:
                if key in group_subject_seminar:
                    return False
                group_subject_seminar[key] = True
    return True

def f4(currentTimetable):
    # Courses can only be held in classrooms with necessary capacity
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie = currentTimetable[profesorIndex][timeIndex]
            sala_info = sala_codes[sala]
            grupa_nume = group_codes[grupa]['nume']
            is_course = len(grupa_nume) == 1
            if is_course and sala_info['curs_posibil'] != 1:
                return False
            if not is_course and sala_info['curs_posibil'] != 0:
                return False
    return True

def f5(currentTimetable):
    # The course must be held before the seminar
    subject_course_times = {}
    subject_seminar_times = {}
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie = currentTimetable[profesorIndex][timeIndex]
            grupa_info = group_codes[grupa]
            grupa_an = grupa_info['an']
            subject_year = grupa_an
            grupa_nume = grupa_info['nume']
            is_course = len(grupa_nume) == 1
            key = (materie, subject_year)
            if is_course:
                if key not in subject_course_times:
                    subject_course_times[key] = []
                subject_course_times[key].append(timeIndex)
            else:
                if key not in subject_seminar_times:
                    subject_seminar_times[key] = []
                subject_seminar_times[key].append(timeIndex)
    for key in subject_seminar_times:
        materie, subject_year = key
        if key in subject_course_times:
            min_course_time = min(subject_course_times[key])
            min_seminar_time = min(subject_seminar_times[key])
            if min_seminar_time <= min_course_time:
                return False
        else:
            return False
    return True

def f6(currentTimetable):
    # The professor can only teach subjects assigned to him
    for profesorIndex in currentTimetable:
        profesor = profesor_codes[profesorIndex]
        subjects_assigned = set(profesor['materiiPredate'])
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie = currentTimetable[profesorIndex][timeIndex]
            if materie not in subjects_assigned:
                return False
    return True

restrictions.append(f1)
restrictions.append(f2)
restrictions.append(f3)
restrictions.append(f4)
restrictions.append(f5)
restrictions.append(f6)

def isTimeTableValid():
    for restriction in restrictions:
        if not restriction(currentTimetable):
            return False
    return True

def calculateTimeTableScoreBasedOnSoftRestrictions():
    # For simplicity, we'll just return a fixed score
    return 1

def addToTimeTable(profesorIndex, timeIndex, grupa, sala, materie):
    profesor = profesor_codes[profesorIndex]
    nrMaximOre = profesor['nrMaximOre']
    if profesorIndex not in currentTimetable:
        currentTimetable[profesorIndex] = {}
    if profesorIndex not in profesor_hours:
        profesor_hours[profesorIndex] = 0
    if profesor_hours[profesorIndex] >= nrMaximOre:
        return False
    if timeIndex in currentTimetable[profesorIndex]:
        return False
    # Check group schedule
    if grupa not in group_schedule:
        group_schedule[grupa] = set()
    if timeIndex in group_schedule[grupa]:
        return False
    # Check sala schedule
    if sala not in sala_schedule:
        sala_schedule[sala] = set()
    if timeIndex in sala_schedule[sala]:
        return False
    # Assign
    currentTimetable[profesorIndex][timeIndex] = (grupa, sala, materie)
    profesor_hours[profesorIndex] += 1
    group_schedule[grupa].add(timeIndex)
    sala_schedule[sala].add(timeIndex)
    return True

def removeFromTimeTable(profesorIndex, timeIndex):
    if profesorIndex in currentTimetable and timeIndex in currentTimetable[profesorIndex]:
        grupa, sala, materie = currentTimetable[profesorIndex][timeIndex]
        del currentTimetable[profesorIndex][timeIndex]
        profesor_hours[profesorIndex] -= 1
        group_schedule[grupa].remove(timeIndex)
        sala_schedule[sala].remove(timeIndex)

# Build the list of classes to schedule
class_list = []

for materie in loadedData['materii']:
    subject_year = materie['an']
    if materie['este_optionala'] == 0:
        # Mandatory subject
        for group in loadedData['grupe']:
            if group['an'] != subject_year:
                continue
            group_nume = group['nume']
            if len(group_nume) == 1:
                # Course group
                class_list.append({
                    'type': 'course',
                    'materie': materie['cod'],
                    'grupa': group['cod']
                })
            else:
                # Seminar group
                class_list.append({
                    'type': 'seminar',
                    'materie': materie['cod'],
                    'grupa': group['cod']
                })
    else:
        # Optional subject
        # Course is for all main groups at once per year
        main_groups = [group for group in loadedData['grupe'] if group['an'] == subject_year and len(group['nume']) == 1]
        for group in main_groups:
            class_list.append({
                'type': 'course',
                'materie': materie['cod'],
                'grupa': group['cod']
            })
        # Seminars for each main group
        for group in main_groups:
            class_list.append({
                'type': 'seminar',
                'materie': materie['cod'],
                'grupa': group['cod']
            })

def backtracking(class_index):
    global bestTimeTable, bestTimeTableScore
    print(class_index)
    if class_index == len(class_list):
        if isTimeTableValid():
            
            bestTimeTable = copy.deepcopy(currentTimetable)
            # bestTimeTableScore = timeTableScore
            return 1
            timeTableScore = calculateTimeTableScoreBasedOnSoftRestrictions()
            if timeTableScore > bestTimeTableScore:
                bestTimeTable = copy.deepcopy(currentTimetable)
                bestTimeTableScore = timeTableScore
        return 0
    cls = class_list[class_index]
    materie = cls['materie']
    grupa = cls['grupa']
    class_type = cls['type']  # 'course' or 'seminar'
    possible_professors = []
    for profesor in loadedData['profesori']:
        if materie in profesor['materiiPredate']:
            profesorIndex = profesor['cod']
            possible_professors.append(profesorIndex)
    for profesorIndex in possible_professors:
        for time in loadedData['timp']:
            timeIndex = time['cod']
            profesor = profesor_codes[profesorIndex]
            if timeIndex in currentTimetable.get(profesorIndex, {}):
                continue
            for sala in loadedData['sali']:
                salaIndex = sala['cod']
                is_course = (class_type == 'course')
                if is_course and sala['curs_posibil'] != 1:
                    continue
                if not is_course and sala['curs_posibil'] != 0:
                    continue
                if timeIndex not in sala['timp_posibil']:
                    continue
                if addToTimeTable(profesorIndex, timeIndex, grupa, salaIndex, materie):
                    # if isTimeTableValid(): # intermediary check not all check
                    returnValue = backtracking(class_index + 1)
                    if returnValue == 1:
                        return 1
                    removeFromTimeTable(profesorIndex, timeIndex)

# Start the backtracking algorithm
backtracking(0)

# Print the best timetable
if bestTimeTable is not None:
    print("Best timetable found with score:", bestTimeTableScore)
    for profesorIndex in bestTimeTable:
        profesor = profesor_codes[profesorIndex]
        print("Professor:", profesor['numeProfesor'])
        for timeIndex in bestTimeTable[profesorIndex]:
            grupa, sala, materie = bestTimeTable[profesorIndex][timeIndex]
            time_info = time_codes[timeIndex]
            sala_info = sala_codes[sala]
            materie_info = materie_codes[materie]
            grupa_info = group_codes[grupa]
            grupa_nume = grupa_info['nume'] + " (Anul {})".format(grupa_info['an'])
            print(f"  Time: {time_info['zi']} {time_info['ora']}")
            print(f"    Group: {grupa_nume}")
            print(f"    Room: {sala_info['nume']}")
            print(f"    Subject: {materie_info['nume']}")
else:
    print("No valid timetable found.")