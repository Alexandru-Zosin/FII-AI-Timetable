import random
import json
import time as t
import copy
import cProfile
from flask import Flask, render_template, url_for

# Keep track of restrictions that are either verified after
# the entire timetable is built (restrictions) or during the assignment
# of each class (during_assignment_restrictions).
restrictions = []
during_assignment_restrictions = []

# JSON files loaded from the 'data' directory
file_names = ['groups', 'subjects', 'teachers', 'rooms', 'time_slots', 'extra_restrictions']
loaded_data = {}

# Loading data from JSON files
for file_name in file_names:
    with open(f'./eng_data/{file_name}.json', 'r') as file:
        read_data = json.load(file)
        loaded_data[file_name] = read_data

# Lookup dictionaries for entities by their codes
# Example: groups[301] gives all info about group 301 (name, language, code)
groups = {group['code']: group for group in loaded_data['groups']}
rooms = {room['code']: room for room in loaded_data['rooms']}
teachers = {teacher['code']: teacher for teacher in loaded_data['teachers']}
subjects = {subject['code']: subject for subject in loaded_data['subjects']}
time_slots = {time['code']: time for time in loaded_data['time_slots']}

# Initializing variables
best_timetable = None
best_timetable_score = 0
# current_timetable[teacher_index][time_index] = (group, room, subject)
current_timetable = {}
# Keeps track of each teacher's assigned hours
teacher_hours = {}
# Keeps track of each group's schedule to detect overlapping classes
group_schedule = {}
# Keeps track of each room's schedule
room_schedule = {}

"""
# Define the restriction functions
# Restriction 1: No overlapping classes for any group
def f1(current_timetable):
    for group, times in group_schedule.items():
        if len(times) != len(set(times)):
            return False
    return True

# Restriction 2: All mandatory subjects are assigned to groups
def f2(current_timetable):
    mandatory_subjects = [s['code'] for s in subjects.values() if not s['is_optional']]
    for group in groups.values():
        assigned_subjects = {c[2] for t in current_timetable.values() for c in t.values() if c[0] == group['code']}
        if not set(mandatory_subjects).issubset(assigned_subjects):
            return False
    return True

# Restriction 3: Each group has a subject only once per type
def f3(current_timetable):
    for teacher, schedule in current_timetable.items():
        for time, details in schedule.items():
            group, _, subject, class_type = details
            key = (group, subject)
            if key in group_schedule.get(class_type, set()):
                return False
            group_schedule.setdefault(class_type, set()).add(key)
    return True

# Restriction 4: Courses are only held in rooms that allow them
def f4(current_timetable):
    for teacher, schedule in current_timetable.items():
        for time, details in schedule.items():
            _, room, _, class_type = details
            room_info = rooms[room]
            if class_type == 'course' and not room_info['course_possible']:
                return False
            if class_type == 'seminar' and room_info['course_possible']:
                return False
    return True

# Restriction 5: Courses must occur before seminars
def f5(current_timetable):
    course_times = {}
    seminar_times = {}
    for teacher, schedule in current_timetable.items():
        for time, details in schedule.items():
            group, _, subject, class_type = details
            if class_type == 'course':
                course_times[subject] = time
            elif class_type == 'seminar':
                seminar_times[subject] = time
    for subject in seminar_times:
        if subject in course_times and seminar_times[subject] <= course_times[subject]:
            return False
    return True

# Restriction 6: Teachers can only teach assigned subjects
def f6(current_timetable):
    for teacher, schedule in current_timetable.items():
        for time, details in schedule.items():
            _, _, subject, _ = details
            if subject not in teachers[teacher]['subjects_taught']:
                return False
    return True

# Restriction 7: Only eligible teachers can teach courses
def f7(current_timetable):
    for teacher, schedule in current_timetable.items():
        for time, details in schedule.items():
            group, _, _, class_type = details
            if class_type == 'course' and not teachers[teacher]['can_teach_course']:
                return False
    return True

# restrictions.append(f1)
# restrictions.append(f2)
# restrictions.append(f7)
# restrictions.append(f3)
# restrictions.append(f4)
# restrictions.append(f5)
# restrictions.append(f6)

# during_assignment_restrictions.append(f6)
# during_assignment_restrictions.append(f4)
# during_assignment_restrictions.append(f3)
"""

def is_timetable_valid():
    for restriction in restrictions:
        if not restriction(current_timetable):
            return False
    return True


def add_to_timetable(teacher_index, time_index, group, room, subject, class_type):
    # Initialize teacher's timetable
    if teacher_index not in current_timetable:
        current_timetable[teacher_index] = {}

    # Check group schedule
    if group not in group_schedule:
        group_schedule[group] = set()
    if time_index in group_schedule[group]:
        return False

    # Check room schedule
    if room not in room_schedule:
        room_schedule[room] = set()
    if time_index in room_schedule[room]:
        return False

    # Assign class to timetable
    current_timetable[teacher_index][time_index] = (group, room, subject, class_type)
    teacher_hours[teacher_index] += 1
    group_schedule[group].add(time_index)
    room_schedule[room].add(time_index)
    return True


def remove_from_timetable(teacher_index, time_index):
    if teacher_index in current_timetable and time_index in current_timetable[teacher_index]:
        group, room, subject, class_type = current_timetable[teacher_index][time_index]
        del current_timetable[teacher_index][time_index]
        teacher_hours[teacher_index] -= 1
        group_schedule[group].remove(time_index)
        room_schedule[room].remove(time_index)

# Build the list of classes to schedule
class_list = []
for subject in loaded_data['subjects']:
    if subject['is_optional'] == 0:  # Mandatory subject
        for group in loaded_data['groups']:
            group_name = group['name']
            if len(group_name) == 1:  # Course group
                class_list.append({
                    'type': 'course',
                    'subject': subject['code'],
                    'group': group['code']
                })
            else:  # Seminar group
                class_list.append({
                    'type': 'seminar',
                    'subject': subject['code'],
                    'group': group['code']
                })
    else:  # Optional subject
        main_groups = [group for group in loaded_data['groups'] if len(group['name']) == 1]
        for group in main_groups:
            class_list.append({
                'type': 'course',
                'subject': subject['code'],
                'group': group['code']
            })
            class_list.append({
                'type': 'seminar',
                'subject': subject['code'],
                'group': group['code']
            })

bar_plot_values = []

def backtracking(class_index):
    global best_timetable, best_timetable_score, bar_plot_values

    if class_index == len(class_list):  # Base case
        best_timetable = copy.deepcopy(current_timetable)
        return 1

    cls = class_list[class_index]
    subject = cls['subject']
    group = cls['group']
    class_type = cls['type']  # 'course' or 'seminar'
    possible_teachers = [
        teacher['code'] for teacher in loaded_data['teachers']
        if subject in teacher['subjects_taught']
    ]

    for teacher_index in possible_teachers:
        if class_type == 'course' and not teachers[teacher_index]['can_teach_course']:
            continue

        if teacher_index not in teacher_hours:
            teacher_hours[teacher_index] = 0

        if teacher_hours[teacher_index] >= teachers[teacher_index]['max_hours']:
            continue

        for time in loaded_data['time_slots']:
            time_index = time['code']
            if time_index in group_schedule.get(group, set()):
                continue

            if time_index in current_timetable.get(teacher_index, {}):
                continue

            for room in loaded_data['rooms']:
                room_index = room['code']
                is_course = (class_type == 'course')
                if is_course and not room['course_possible']:
                    continue
                if time_index not in room['possible_times']:
                    continue

                if add_to_timetable(teacher_index, time_index, group, room_index, subject, class_type):
                    return_value = backtracking(class_index + 1)
                    if return_value == 1:
                        return 1
                    remove_from_timetable(teacher_index, time_index)

backtracking(0)

# Transform the final timetable into a structured format for the UI
def transform_data(best_timetable):
    timetable_data = {}
    for teacher_index, schedule in best_timetable.items():
        teacher = teachers[teacher_index]["name"]
        for time_index, details in schedule.items():
            group, room, subject, class_type = details
            day = time_slots[time_index]["day"]
            hour = time_slots[time_index]["hour"]
            interval = f"{hour[:2]}-{str(int(hour[:2]) + 2).zfill(2)}"

            row = {
                "Interval": interval,
                "Subject": subjects[subject]["name"],
                "Teacher": teacher,
                "Room": rooms[room]["name"],
                "Type": class_type
            }

            timetable_data.setdefault(group, {}).setdefault(day, []).append(row)

    for group in timetable_data:
        for day in timetable_data[group]:
            timetable_data[group][day] = sorted(timetable_data[group][day], key=lambda x: x["Interval"])

    return timetable_data


transformed_timetable = transform_data(best_timetable)

app = Flask(__name__)

@app.route('/')
def index():
    groups = transformed_timetable.keys()
    return render_template('eng_index.html', groups=groups)

@app.route('/timetable/<int:group>')
def timetable(group):
    if group not in transformed_timetable:
        return "Timetable for this group is not available.", 404

    data = transformed_timetable[group]
    return render_template('eng_timetable.html', group=group, timetable_data=data)

app.run(debug=True)