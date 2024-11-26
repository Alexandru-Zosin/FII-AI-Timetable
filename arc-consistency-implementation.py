import random
import json
import time as t
import copy
import cProfile
import matplotlib.pyplot as plt
from flask import Flask, render_template, url_for
import pandas as pd

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

# Define the initial domains for each variable (class)
variable_domains = {}  # variable_domains[class_index] = list of possible assignments
for class_index, cls in enumerate(class_list):
    variable_domains[class_index] = []
    materie = cls['materie']
    grupa = cls['grupa']
    class_type = cls['type']  # 'course' or 'seminar'

    possible_professors = []

    for profesor in loadedData['profesori']:
        if materie in profesor['materiiPredate']:
            profesorIndex = profesor['cod']

            # Check if the professor can teach courses/seminars
            if class_type == 'course' and profesor['poatePredaCurs'] == 0:
                continue

            possible_professors.append(profesorIndex)

    for profesorIndex in possible_professors:
        profesor = profesor_codes[profesorIndex]
        for time in loadedData['timp']:
            timeIndex = time['cod']
            for sala in loadedData['sali']:
                salaIndex = sala['cod']
                is_course = (class_type == 'course')
                if is_course and sala['curs_posibil'] != 1:
                    continue
                if not is_course and sala['curs_posibil'] != 0:
                    continue
                if timeIndex not in sala['timp_posibil']:
                    continue  # Room is not available at this time

                # You can add additional constraints here if necessary
                assignment = (profesorIndex, timeIndex, salaIndex)
                variable_domains[class_index].append(assignment)

# Define Neighbors for each variable
Neighbors = {}  # Neighbors[Xi] = set of indices of neighboring variables
for i in range(len(class_list)):
    Neighbors[i] = set()

for i in range(len(class_list)):
    Xi = class_list[i]
    for j in range(len(class_list)):
        if i == j:
            continue
        Xj = class_list[j]

        # If they share the same group
        if Xi['grupa'] == Xj['grupa']:
            Neighbors[i].add(j)
            continue

        # If they can possibly be assigned the same professor
        possible_professors_i = set(assignment[0] for assignment in variable_domains[i])
        possible_professors_j = set(assignment[0] for assignment in variable_domains[j])
        if possible_professors_i & possible_professors_j:
            Neighbors[i].add(j)
            continue

        # If they can possibly be assigned the same room
        possible_rooms_i = set(assignment[2] for assignment in variable_domains[i])
        possible_rooms_j = set(assignment[2] for assignment in variable_domains[j])
        if possible_rooms_i & possible_rooms_j:
            Neighbors[i].add(j)
            continue

        # Course before seminar constraint
        if Xi['materie'] == Xj['materie'] and Xi['grupa'] == Xj['grupa']:
            if (Xi['type'] == 'course' and Xj['type'] == 'seminar') or (Xi['type'] == 'seminar' and Xj['type'] == 'course'):
                Neighbors[i].add(j)
                continue

# Implement the AC-3 Algorithm
def is_consistent(xi, xj, Xi, Xj):
    prof_i, time_i, room_i = xi
    prof_j, time_j, room_j = xj

    # If Xi and Xj share the same group
    if Xi['grupa'] == Xj['grupa']:
        if time_i == time_j:
            return False

    # If the professors are the same
    if prof_i == prof_j:
        if time_i == time_j:
            return False

    # If the rooms are the same
    if room_i == room_j:
        if time_i == time_j:
            return False

    # Course before seminar constraint
    if Xi['materie'] == Xj['materie'] and Xi['grupa'] == Xj['grupa']:
        if Xi['type'] == 'course' and Xj['type'] == 'seminar':
            if time_i >= time_j:
                return False
        if Xi['type'] == 'seminar' and Xj['type'] == 'course':
            if time_j >= time_i:
                return False

    return True

def remove_inconsistent_values(Xi, Xj, variable_domains):
    removed = False
    domain_xi = variable_domains[Xi]
    domain_xj = variable_domains[Xj]
    new_domain_xi = []

    for x in domain_xi:
        found = False
        for y in domain_xj:
            if is_consistent(x, y, class_list[Xi], class_list[Xj]):
                found = True
                break
        if found:
            new_domain_xi.append(x)
        else:
            removed = True
    if removed:
        variable_domains[Xi] = new_domain_xi
    return removed

def AC3(variable_domains):
    queue = []
    for Xi in range(len(class_list)):
        for Xj in Neighbors[Xi]:
            queue.append((Xi, Xj))
    while queue:
        (Xi, Xj) = queue.pop(0)
        if remove_inconsistent_values(Xi, Xj, variable_domains):
            if len(variable_domains[Xi]) == 0:
                return False  # Failure
            for Xk in Neighbors[Xi]:
                if Xk != Xj:
                    queue.append((Xk, Xi))
    return True  # Success

# Apply AC-3 Algorithm as Preprocessing
variable_domains_preAC3 = copy.deepcopy(variable_domains)  # Keep a copy for comparison
if not AC3(variable_domains):
    print("No solution possible after AC-3 preprocessing.")
else:
    print("Domains after AC-3 preprocessing:")
    for Xi in range(len(class_list)):
        cls = class_list[Xi]
        print(f"Variable {Xi} ({cls['type']} of subject {cls['materie']} for group {cls['grupa']}):")
        domain = variable_domains[Xi]
        print(f"  Domain size: {len(domain)}")
        # Uncomment the following lines to print the actual domain values
        # for value in domain:
        #     prof_i, time_i, room_i = value
        #     print(f"    Professor {prof_i}, Time {time_i}, Room {room_i}")
    print()

# Integrate AC-3 into Backtracking
def backtracking(assignment, variable_domains):
    if len(assignment) == len(class_list):
        # All variables assigned
        return assignment

    # Select unassigned variable Xi (using MRV heuristic)
    unassigned_vars = [Xi for Xi in range(len(class_list)) if Xi not in assignment]
    Xi = min(unassigned_vars, key=lambda var: len(variable_domains[var]))

    # For each value in variable_domains[Xi]:
    domain_Xi = variable_domains[Xi]

    for value in domain_Xi:
        # Create a deep copy of variable_domains
        new_variable_domains = copy.deepcopy(variable_domains)

        assignment[Xi] = value

        # Reduce the domain of Xi to [value]
        new_variable_domains[Xi] = [value]

        # Apply AC-3
        if AC3(new_variable_domains):
            result = backtracking(assignment, new_variable_domains)
            if result is not None:
                return result
        # Remove assignment
        del assignment[Xi]

    return None  # Failure

# Solve the CSP using backtracking with AC-3
assignment = {}
solution = backtracking(assignment, variable_domains)

if solution is None:
    print("No solution found.")
else:
    print("Solution found:")
    for Xi in range(len(class_list)):
        cls = class_list[Xi]
        value = solution[Xi]
        prof_i, time_i, room_i = value
        print(f"Class {Xi}: {cls['type']} of subject {cls['materie']} for group {cls['grupa']}")
        print(f"  Assigned to Professor {prof_i}, Time {time_i}, Room {room_i}")
    print()

# Optionally, you can compare with the original backtracking without AC-3
# For comparison purposes, you can implement the original backtracking function without AC-3 and measure the time or steps required to find a solution.

# Example of comparison code (simplified):

import time

def backtracking_without_AC3(assignment):
    if len(assignment) == len(class_list):
        # All variables assigned
        return assignment

    # Select unassigned variable Xi (using MRV heuristic)
    unassigned_vars = [Xi for Xi in range(len(class_list)) if Xi not in assignment]
    Xi = min(unassigned_vars, key=lambda var: len(variable_domains_preAC3[var]))

    # For each value in variable_domains_preAC3[Xi]:
    domain_Xi = variable_domains_preAC3[Xi]

    for value in domain_Xi:
        consistent = True
        # Check consistency with assignment
        for Xj in assignment:
            if not is_consistent(value, assignment[Xj], class_list[Xi], class_list[Xj]):
                consistent = False
                break
        if consistent:
            assignment[Xi] = value
            result = backtracking_without_AC3(assignment)
            if result is not None:
                return result
            del assignment[Xi]

    return None  # Failure

# Measure time for backtracking without AC-3
start_time = time.time()
assignment = {}
solution_no_AC3 = backtracking_without_AC3(assignment)
end_time = time.time()
time_no_AC3 = end_time - start_time

# Measure time for backtracking with AC-3
start_time = time.time()
assignment = {}
solution_with_AC3 = backtracking({}, variable_domains)
end_time = time.time()
time_with_AC3 = end_time - start_time

print(f"Time without AC-3: {time_no_AC3} seconds")
print(f"Time with AC-3: {time_with_AC3} seconds")

# Add this at the top of arc-consistency-implementation.py
from flask import Flask, render_template
app = Flask(__name__)

# Modify the output section to store solution in the same format as main.py
def format_solution(solution, class_list):
    formatted_timetable = {}
    for Xi in range(len(class_list)):
        cls = class_list[Xi]
        value = solution[Xi]
        prof_i, time_i, room_i = value
        
        if prof_i not in formatted_timetable:
            formatted_timetable[prof_i] = {}
            
        formatted_timetable[prof_i][time_i] = (
            cls['grupa'], 
            room_i, 
            cls['materie'], 
            cls['type']
        )
    return formatted_timetable

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
# Replace existing output code with:
if solution:
    formatted_timetable = format_solution(solution, class_list)
    timetable_data = transform_data(formatted_timetable, profesor_codes, time_codes, sala_codes, materie_codes, group_codes)
    
    @app.route('/')
    def index():
        groups = timetable_data.keys()
        return render_template('index.html', groups=groups)

    @app.route('/timetable/<int:group>')
    def timetable(group):
        if group not in timetable_data:
            return "Orarul pentru această grupă nu este disponibil.", 404
        data = timetable_data[group]
        return render_template('timetable.html', group=group, timetable_data=data)

    app.run(debug=True)
else:
    print("No solution found")
