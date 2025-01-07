import random
import json
import time as t
import copy
import cProfile
from flask import Flask, render_template, url_for
restrictions = []
duringConstructionRestrictions = []
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

required_subjects = [subject['cod'] for subject in loadedData['materii'] if subject['este_optionala'] == 0]
required_subjects_set = set(required_subjects)
optional_subjects = [subject['cod'] for subject in loadedData['materii'] if subject['este_optionala'] == 1]
optional_subjects_set = set(optional_subjects)

def f2(currentTimetable):
    # Each group has assigned all mandatory subjects
    global required_subjects_set
    group_subjects = {}
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
            if grupa not in group_subjects:
                group_subjects[grupa] = set()
            if materie in required_subjects:
                group_subjects[grupa].add(materie)
    for grupa in group_codes:
        if grupa not in group_subjects:
            assigned_subjects = set()
        else:
            assigned_subjects = group_subjects[grupa]
        if len(required_subjects_set) != len(assigned_subjects):
            return False
    return True

def f3(currentTimetable):
    # A group has classes for a subject only once (max one course, max one seminar)
    group_subject_course = {}
    group_subject_seminar = {}
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie, class_type= currentTimetable[profesorIndex][timeIndex]
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
    # The course must be held before the seminar
    subject_course_times = {}
    subject_seminar_times = {}
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
    for key in subject_seminar_times:
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
            grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
            if materie not in subjects_assigned:
                return False
    return True

def f7(currentTimetable):
    # The course is only assigned to a professor that can teach at a course
    for profesorIndex in currentTimetable:
        for timeIndex in currentTimetable[profesorIndex]:
            grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
            profesor = profesor_codes[profesorIndex]
            if len(group_codes[grupa]['nume']) == 1 and profesor['poatePredaCurs'] == 0:
                return False
    return True
# restrictions.append(f1)
# restrictions.append(f2)
# restrictions.append(f7)
# restrictions.append(f3) # posibil de scos
# restrictions.append(f4) # posibil de scos 
# restrictions.append(f5) # posibil de scos ca nu ne intereseaza
# restrictions.append(f6) # possibil de scos

# duringConstructionRestrictions.append(f6)
# duringConstructionRestrictions.append(f4)
# duringConstructionRestrictions.append(f3)

def isTimeTableValid():
    for restriction in restrictions:
        if not restriction(currentTimetable):
            return False
    return True

def checkRequirementsDuringConstruction():
    for dTypeRestriction in duringConstructionRestrictions:
        if not dTypeRestriction(currentTimetable):
            return False
    return True

def calculateTimeTableScoreBasedOnSoftRestrictions():
    # For simplicity, we'll just return a fixed score
    return 1

def addToTimeTable(profesorIndex, timeIndex, grupa, sala, materie, class_type):
    # we could've checked if the professor can teach the course here
    if profesorIndex not in currentTimetable:
        currentTimetable[profesorIndex] = {}
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
    currentTimetable[profesorIndex][timeIndex] = (grupa, sala, materie, class_type)
    profesor_hours[profesorIndex] += 1
    group_schedule[grupa].add(timeIndex)
    sala_schedule[sala].add(timeIndex)
    return True

def removeFromTimeTable(profesorIndex, timeIndex):
    if profesorIndex in currentTimetable and timeIndex in currentTimetable[profesorIndex]:
        grupa, sala, materie, class_type = currentTimetable[profesorIndex][timeIndex]
        del currentTimetable[profesorIndex][timeIndex]
        profesor_hours[profesorIndex] -= 1
        group_schedule[grupa].remove(timeIndex)
        sala_schedule[sala].remove(timeIndex)

# Build the list of classes to schedule
class_list = []

for materie in loadedData['materii']:
    if materie['este_optionala'] == 0:
        # Mandatory subject
        for group in loadedData['grupe']:
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
        main_groups = [group for group in loadedData['grupe'] if len(group['nume']) == 1]
        for group in main_groups:
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

# class_list.sort(key=lambda x: x['type'] == 'seminar')

bar_plot_values = []

def backtracking(class_index):
    global bestTimeTable, bestTimeTableScore, bar_plot_values

    if class_index == len(class_list):  # base case
        if isTimeTableValid():
            bestTimeTable = copy.deepcopy(currentTimetable)
            return 1
        return 0

    cls = class_list[class_index]
    materie = cls['materie']
    grupa = cls['grupa']
    class_type = cls['type']  # 'course' or 'seminar'
    possible_professors = []

    for profesor in loadedData['profesori']:  # iterates over all professors for this materie (this cls)
        if materie in profesor['materiiPredate']:
            profesorIndex = profesor['cod']
            possible_professors.append(profesorIndex)
    for profesorIndex in possible_professors:
        # here we check if a professor can teach courses
        if class_type == 'course' and profesor_codes[profesorIndex]['poatePredaCurs'] == 0:
            continue
        profesor = profesor_codes[profesorIndex]
        nrMaximOre = profesor['nrMaximOre']
        if profesorIndex not in profesor_hours:
            profesor_hours[profesorIndex] = 0
        if profesor_hours[profesorIndex] >= nrMaximOre:
            continue
        for time in loadedData['timp']:  # iterates over all possible time slots
            timeIndex = time['cod']
            if timeIndex in group_schedule.get(grupa, {}):
                continue

            profesor = profesor_codes[profesorIndex]
            if timeIndex in currentTimetable.get(profesorIndex, {}):
                continue  # check if professor is already busy then in that timeslot

            for sala in loadedData['sali']: # iterates over all possible classrooms
                salaIndex = sala['cod']
                is_course = (class_type == 'course')
                if is_course and sala['curs_posibil'] != 1:
                    continue
                if timeIndex not in sala['timp_posibil']:
                    continue

                if addToTimeTable(profesorIndex, timeIndex, grupa, salaIndex, materie, class_type):

                    returnValue = backtracking(class_index + 1)
                    if returnValue == 1:
                        return 1
                    removeFromTimeTable(profesorIndex, timeIndex)

backtracking(0)

def transform_data(bestTimeTable, profesor_codes, time_codes, sala_codes, materie_codes, group_codes):
    timetable_data = {}

    for profesorIndex, schedule in bestTimeTable.items():
        profesor = profesor_codes[profesorIndex]["numeProfesor"]

        for timeIndex, details in schedule.items():
            grupa, sala, materie, class_type = details
            zi = time_codes[timeIndex]["zi"]
            ora = time_codes[timeIndex]["ora"]
            interval = f"{ora[:2]}-{str(int(ora[:2]) + 2).zfill(2)}"  # ex: 08:00 -> "08-10"
            
            # Formatează datele într-un rând structurat
            row = {
                "Interval": interval,
                "Disciplina": materie_codes[materie]["nume"],
                "Profesor": profesor,
                "Sala": sala_codes[sala]["nume"],
                "Tip": class_type # Poți adapta pentru frecvență dacă există informații suplimentare
            }

            # Inițializează ziua și grupa în `timetable_data`
            timetable_data.setdefault(grupa, {}).setdefault(zi, []).append(row)

    # Sortează intervalele orare pentru fiecare zi și grupă
    for grupa in timetable_data:
        for zi in timetable_data[grupa]:
            timetable_data[grupa][zi] = sorted(timetable_data[grupa][zi], key=lambda x: x["Interval"])

    return timetable_data


timetable_data = transform_data(bestTimeTable, profesor_codes, time_codes, sala_codes, materie_codes, group_codes)


app = Flask(__name__)

# Pagina principală cu lista grupelor
@app.route('/')
def index():
    groups = timetable_data.keys()
    return render_template('index.html', groups=groups)

# Pagină individuală pentru fiecare orar de grupă
@app.route('/timetable/<int:group>')
def timetable(group):
    if group not in timetable_data:
        return "Orarul pentru această grupă nu este disponibil.", 404
    
    data = timetable_data[group]
    return render_template('timetable.html', group=group, timetable_data=data)


app.run(debug=True)