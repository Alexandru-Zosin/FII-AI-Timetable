import random
import json
import time as t
import copy
import cProfile
from flask import Flask, render_template, url_for

"""
Restrictions (MANDATORY):
#  1) Mandatory subjects are assigned to each group.
#  2) No overlapping classes for the same group at the same time.
#  3) A teacher does not teach two classes at the same time.
#  4) A room cannot have two classes at the same time.
#  5) A course must be taught in a room that supports courses.
#  6) Seminars must be in rooms that do NOT support courses.
#  7) A professor cannot exceed max teaching hours.
#  8) Courses must be scheduled before seminars for the same subject & group.
"""

# keeps track of restrictions (verf. after entire timetable is built or during)
restrictions = []
during_assignment_restrictions = []

# JSON filenames loaded from the 'eng_data' directory
file_names = ['groups', 'subjects', 'teachers', 'rooms', 'time_slots', 'extra_restrictions']
loaded_data = {}
# loading data from JSON files
for file_name in file_names:
    with open(f'./eng_data/{file_name}.json', 'r') as file:
        read_data = json.load(file)
        loaded_data[file_name] = read_data

# lookup dictionaries for entities accessed by codes
# example: groups[301] gives all info about group 301 (name, language, code)
groups = {group['code']: group for group in loaded_data['groups']}
rooms = {room['code']: room for room in loaded_data['rooms']}
teachers = {teacher['code']: teacher for teacher in loaded_data['teachers']}
subjects = {subject['code']: subject for subject in loaded_data['subjects']}
time_slots = {time['code']: time for time in loaded_data['time_slots']}

best_timetable = None
best_timetable_score = 0

current_timetable = {}  # current_timetable[teacher_code][time_code] = (group_code, room_code, subject_code, class_type)
teacher_schedule = {}  # which timeslots are occupied by each teacher
group_schedule = {}  # which timeslots are occupied by each group -> detect overlapping classes
room_schedule = {}  # which time slots are occupied by each room

# builds the list of classes to schedule (courses & seminars)
# a class is (GROUP_code + SUBJECT_code + class_TYPE(course/seminar))
class_list = []
for subject in loaded_data['subjects']:
    if subject['is_optional'] == 0:  # mandatory subject
        for group in loaded_data['groups']:
            group_name = group['name']
            if len(group_name) == 1:  # course group(all subgroups altogether)
                class_list.append({
                    'type': 'course',
                    'subject_code': subject['code'],
                    'group_code': group['code']
                })
            else:  # seminar group (each individual group)
                class_list.append({
                    'type': 'seminar',
                    'subject_code': subject['code'],
                    'group_code': group['code']
                })
    else:  # optional subject
        main_groups = [group for group in loaded_data['groups'] if len(group['name']) == 1]
        for group in main_groups:
            class_list.append({
                'type': 'course',
                'subject_code': subject['code'],
                'group_code': group['code']
            })
            class_list.append({
                'type': 'seminar',
                'subject_code': subject['code'],
                'group_code': group['code']
            })

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

def is_timetable_valid():
    for restriction in restrictions:
        if not restriction(current_timetable):
            return False
    return True
"""

def add_to_timetable(teacher_code, time_code, group_code, room_code, subject_code, class_type):
    """
    Attempts to add a class (group_code, room_code, subject_code, class_type)
    to current_timetable[teacher_code][time_code]. 
    True if successful
    1) verifies the group is not already in group_schedule at that time
    2) verifies the room is free at the given timeslot
    3) increments teacher_schedule[teacher_code]
    """
    # initialize teacher in timetable if needed
    if teacher_code not in current_timetable:
        current_timetable[teacher_code] = {}

    # checks group schedule
    if group_code not in group_schedule:
        group_schedule[group_code] = set()
    if time_code in group_schedule[group_code]:
        return False

    # checks room schedule
    if room_code not in room_schedule:
        room_schedule[room_code] = set()
    if time_code in room_schedule[room_code]:
        return False

    # assigns class to timetable
    current_timetable[teacher_code][time_code] = (group_code, room_code, subject_code, class_type)
    teacher_schedule[teacher_code] += 1
    group_schedule[group_code].add(time_code)
    room_schedule[room_code].add(time_code)
    return True

def remove_from_timetable(teacher_code, time_code):
    """
    Removes an assignment from the timetable and updates schedule structures
    accordingly.
    """
    if teacher_code in current_timetable and time_code in current_timetable[teacher_code]:
        group_code, room_code, _, _ = current_timetable[teacher_code][time_code]
        del current_timetable[teacher_code][time_code]
        teacher_schedule[teacher_code] -= 1
        group_schedule[group_code].remove(time_code)
        room_schedule[room_code].remove(time_code)

bar_plot_values = []

# we TRY to assign each class(group, subject, type) to a
#                            (teacher, time_slot, room)
# ensuring no overlapping constraints
def backtracking(class_index):
    global best_timetable, best_timetable_score, bar_plot_values

    # base case: if we've processed all classes, success
    if class_index == len(class_list):
        best_timetable = copy.deepcopy(current_timetable)
        return 1

    cls = class_list[class_index]
    subject_code = cls['subject_code']
    group_code = cls['group_code']
    class_type = cls['type']

    # which teachers can teach this subject?
    possible_teachers = [
        teacher['code'] for teacher in loaded_data['teachers']
        if subject_code in teacher['subjects_taught']
    ]

    # WE TRY to assign each TEACHER in turn
    for teacher_code in possible_teachers:
        # if it's a course, we need to check if teacher is elligible
        if class_type == 'course' and not teachers[teacher_code]['can_teach_course']:
            continue
        
        # we initialize teacher_schedule if it's not present
        if teacher_code not in teacher_schedule:
            teacher_schedule[teacher_code] = 0

        # we check that teacher is below his maximum hours
        if teacher_schedule[teacher_code] >= teachers[teacher_code]['max_hours']:
            continue
        
        # WE TRY each possible TIMESLOT
        for time in loaded_data['time_slots']:
            time_code = time['code']
            
            # if the group is already busy, we skip
            if time_code in group_schedule.get(group_code, set()):
                continue
            
            # if the teacher is already busy, we skip
            if time_code in current_timetable.get(teacher_code, {}):
                continue

            # WE TRY each possible ROOM
            for room in loaded_data['rooms']:
                room_code = room['code']
                is_course = (class_type == 'course')

                # if the room doesn't allow courses, we skip
                if is_course and not room['course_possible']:
                    continue
                
                # if the room is not available at this timeslot, we skip
                if time_code not in room['possible_times']:
                    continue

                # attempt to assign
                if add_to_timetable(teacher_code, time_code, group_code, room_code, subject_code, class_type):
                    return_value = backtracking(class_index + 1)
                    if return_value == 1:
                        return 1
                    # if not successful, we remove the assignment
                    remove_from_timetable(teacher_code, time_code)

# starting the backtracking from class_index = 0 (first one)
backtracking(0)

# transforming the final timetable into a structured format for the UI
def transform_data(best_timetable):
    timetable_data = {}
    for teacher_code, schedule in best_timetable.items():
        teacher = teachers[teacher_code]["name"]
        for time_code, details in schedule.items():
            group_code, room_code, subject_code, class_type = details
            day = time_slots[time_code]["day"]
            hour = time_slots[time_code]["hour"]
            interval = f"{hour[:2]}-{str(int(hour[:2]) + 2).zfill(2)}"

            row = {
                "Interval": interval,
                "Subject": subjects[subject_code]["name"],
                "Teacher": teacher,
                "Room": rooms[room_code]["name"],
                "Type": class_type
            }

            timetable_data.setdefault(group_code, {}).setdefault(day, []).append(row)

    for group_code in timetable_data:
        for day in timetable_data[group_code]:
            timetable_data[group_code][day] = sorted(timetable_data[group_code][day], key=lambda x: x["Interval"])

    return timetable_data

transformed_timetable = transform_data(best_timetable)

app = Flask(__name__)

@app.route('/')
def index():
    groups = transformed_timetable.keys()
    return render_template('eng_index.html', groups=groups)

@app.route('/timetable/<int:group_code>')
def timetable(group_code):
    if group_code not in transformed_timetable:
        return "Timetable for this group is not available.", 404

    data = transformed_timetable[group_code]
    return render_template('eng_timetable.html', group=group_code, timetable_data=data)

app.run(debug=True)
