import json
import copy
import cProfile
from flask import Flask, render_template
import threading
import re
from openai import OpenAI

"""
--- can be searched in code with "E1", "R3", ... ---
Restrictions (MANDATORY):
#  R1) Mandatory subjects are assigned to each group.                          ###DONE
#  R2) No overlapping classes for the same group at the same time.             ###DONE
#  R3) A teacher does not teach two classes at the same time.                  ###DONE
#  R4) A room must be available to the university at the given time.           ###DONE
#R4.1) A room cannot have two classes at the same time.                        ###DONE
#  R5) A course must be taught in a room that supports courses.                ###DONE
#  R6) A professor cannot exceed max teaching hours.                           ###DONE
#  R7) No overlapping courses with seminars for a subject at the same time. 
#  R8) A course can be taught only by an elligible teacher.                    ###DONE
Extra restrictions (POSSIBLE):                                                 #-----#
#  E1) A professor can have a number of maximum daily teaching hours           ###DONE
#  E2) A professor can have unpreferred timeslots                              ###DONE
WIP:
#  OP1) Courses must be scheduled before seminars for the same subject & group.
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

# lookup dictionaries for entities accessed by codes(group['code'])
# example: groups[301] gives all info about group 301 (name, language, code)
groups = {group['code']: group for group in loaded_data['groups']}
rooms = {room['code']: room for room in loaded_data['rooms']}
teachers = {teacher['code']: teacher for teacher in loaded_data['teachers']}
subjects = {subject['code']: subject for subject in loaded_data['subjects']}
time_slots = {time['code']: time for time in loaded_data['time_slots']}
extra_restrictions = loaded_data['extra_restrictions']

# builds the list of classes to schedule (courses & seminars)
# a class is (GROUP_code + SUBJECT_code + class_TYPE(course/seminar))
# group_code == 0 means EVERYONE
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
            elif group['code'] != 0:  # seminar group (each individual group) --- avoids EVERYONE
                class_list.append({
                    'type': 'seminar',
                    'subject_code': subject['code'],
                    'group_code': group['code']
                })
    else:  # optional subject
        main_groups = [group for group in loaded_data['groups'] if len(group['name']) == 1]
        class_list.append({ 
                'type': 'course',
                'subject_code': subject['code'],
                'group_code': 0 # course is for EVERYONE at the same time
            })
        for group in main_groups: # seminar is for all respective(A or B or ...) subgroups altogether
            class_list.append({
                'type': 'seminar',
                'subject_code': subject['code'],
                'group_code': group['code']
            })

best_timetable = None

current_timetable = {}  # current_timetable[teacher_code][time_code] = (group_code, room_code, subject_code, class_type)
teacher_schedule = {}  # which timeslots are occupied by each teacher
group_schedule = {}  # which timeslots are occupied by each group -> detect overlapping classes
room_schedule = {}  # which time slots are occupied by each room
daily_teacher_hours = {}  # daily hours for each teacher per day

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

    # initialize group in schedule if needed
    if group_code not in group_schedule:
        group_schedule[group_code] = set()

    # if it's a main group (A, B, C...), ensure no sub-group conflicts
    if len(groups[group_code]['name']) == 1:
        for group in groups.values():
            if str(group['code']).startswith(str(group_code)) and str(group_code) != str(group['code']):
                if group['code'] not in group_schedule:
                    group_schedule[group['code']] = set()
                if time_code in group_schedule[group['code']]:
                    return False
        if 0 not in group_schedule: # EVERYONE
            group_schedule[0] = set()
        if time_code in group_schedule[0]: # if (someone from) EVERYONE is already busy
            return False

    if group_code == 0: # EVERYONE
        for group in groups.values():
            if group['code'] == 0:
                continue # we don't compare it against itself
            if group['code'] not in group_schedule:
                group_schedule[group['code']] = set()
            if time_code in group_schedule[group['code']]:
                return False

    # checks room schedule (R4.1)
    if room_code not in room_schedule:
        room_schedule[room_code] = set()
    if time_code in room_schedule[room_code]:
        return False

    # handling extra restrictions (E1, E2, etc.)
    day = time_slots[time_code]["day"]
    daily_teacher_hours.setdefault(teacher_code, {}).setdefault(day, 0)
    max_daily_hours = extra_restrictions.get("max_daily_hours", {}).get(str(teacher_code), teachers[teacher_code]["max_hours"])
    if daily_teacher_hours[teacher_code][day] + 1 > max_daily_hours:  # E1
        return False
    unpreferred_slots = extra_restrictions.get("unpreferred_timeslots", {}).get(str(teacher_code), [])
    if time_code in unpreferred_slots:  # E2
        return False

    # assigns class to timetable
    current_timetable[teacher_code][time_code] = (group_code, room_code, subject_code, class_type)
    teacher_schedule[teacher_code] += 1
    group_schedule[group_code].add(time_code)
    room_schedule[room_code].add(time_code)
    daily_teacher_hours[teacher_code][day] += 1
    return True

def remove_from_timetable(teacher_code, time_code):
    """
    Removes an assignment from the timetable and updates schedule structures
    accordingly.
    """
    if teacher_code in current_timetable and time_code in current_timetable[teacher_code]:
        group_code, room_code, _, _ = current_timetable[teacher_code][time_code]
        day = time_slots[time_code]["day"]
        del current_timetable[teacher_code][time_code]
        teacher_schedule[teacher_code] -= 1
        group_schedule[group_code].remove(time_code)
        room_schedule[room_code].remove(time_code)
        daily_teacher_hours[teacher_code][day] -= 1

def backtracking(class_index):
    """
    We TRY to assign each class(group, subject, type) to a
    (TEACHER, TIMESLOT, ROOM) ensuring no overlapping constraints
    """
    global best_timetable

    # base case: if we've processed all classes, success (R1)
    if class_index == len(class_list):
        best_timetable = copy.deepcopy(current_timetable)
        return 1

    cls = class_list[class_index]
    subject_code = cls['subject_code']
    group_code = cls['group_code']
    class_type = cls['type']

    # we iterate only through teachers which can teach this subject
    possible_teachers = [
        teacher['code'] for teacher in loaded_data['teachers']
        if subject_code in teacher['subjects_taught']
    ]

    # WE TRY to assign each TEACHER in turn
    for teacher_code in possible_teachers:
        # if it's a course, we need to check if teacher is elligible (R8)
        if class_type == 'course' and not teachers[teacher_code]['can_teach_course']:
            continue
        
        # we initialize teacher_schedule if it's not present
        if teacher_code not in teacher_schedule:
            teacher_schedule[teacher_code] = 0

        # check that teacher is below his maximum weekly hours (R6)
        if teacher_schedule[teacher_code] >= teachers[teacher_code]['max_hours']:
            continue
        
        # WE TRY each possible TIMESLOT
        for time in loaded_data['time_slots']:
            time_code = time['code']
            
            # if the group is already busy, skip (R2)
            if time_code in group_schedule.get(group_code, set()):
                continue
            
            # if the teacher is already busy, skip (R3)
            if time_code in current_timetable.get(teacher_code, {}):
                continue

            # WE TRY each possible ROOM
            for room in loaded_data['rooms']:
                room_code = room['code']
                is_course = (class_type == 'course')

                # if the room doesn't allow courses, skip (R5)
                if is_course and not room['course_possible']:
                    continue
                
                # if the room is not available at this timeslot, skip (R4)
                if time_code not in room['possible_times']:
                    continue

                # attempt to assign
                if add_to_timetable(teacher_code, time_code, group_code, room_code, subject_code, class_type):
                    return_value = backtracking(class_index + 1)
                    if return_value == 1:
                        return 1
                    # if not successful, remove assignment
                    remove_from_timetable(teacher_code, time_code)

def transform_data(best_timetable):
    """
    Transforms the final timetable into a structured format for the UI.
    """
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
            if group_code != 0:
                timetable_data.setdefault(group_code, {}).setdefault(day, []).append(row)
            else: 
                # in case of EVERYONE, replicate for each main group (A,B,C,...)
                main_groups = [code for code, group in groups.items() if len(group['name']) == 1]
                for main_group in main_groups:
                    timetable_data.setdefault(main_group, {}).setdefault(day, []).append(row)

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]  # order of days for sorting
    for group_code in timetable_data:
        for day in timetable_data[group_code]:
            timetable_data[group_code][day] = sorted(timetable_data[group_code][day], key=lambda x: x["Interval"])
        timetable_data[group_code] = {
            day: timetable_data[group_code][day]
            for day in sorted(timetable_data[group_code].keys(), key=lambda d: day_order.index(d))
        }

    return timetable_data

# Initial run of the scheduling
backtracking(0)
a = 1
transformed_timetable = transform_data(best_timetable)

app = Flask(__name__)

@app.route('/')
def index():
    global transformed_timetable
    groups = transformed_timetable.keys()
    return render_template('eng_index.html', groups=groups)

@app.route('/timetable/<int:group_code>')
def timetable(group_code):
    global transformed_timetable
    if group_code not in transformed_timetable:
        return "Timetable for this group is not available.", 404

    data = transformed_timetable[group_code]
    return render_template('eng_timetable.html', group=group_code, timetable_data=data)

# ------------------------------------------------------------------------------------
# NEW CODE: prompt in console to add restrictions + re-generate timetable
# ------------------------------------------------------------------------------------

def parse_prompt_and_add_restrictions(line, extra_restrictions):
    global teachers, time_slots, subjects

    prompt = f"""
    You are a helpful assistent that based on an user input have to generate a JSON file matching the requirments
    We are running a timetable generative app and you are tasked with understanding what extra restrictions are described 
    by the user input and generating a JSON to match that

    You have to select from two kinds of restrictions, but the number of restrictions generated is not limited
    The types of restrictions are
    1. Unpreffered time slots: this maps the professor code id's to the timeslots ids that are not to be used for that proffesor 
    2. Max daily hours: which maps a professor id to the maximum number of daily hours 

    Here is an example 
    """ + """
    {
        "unpreferred_timeslots": {
            "2": [1, 12],
            "3": [1, 2]
        },
        "max_daily_hours": {
            "2": 2,
            "3": 3
        }
    }""" + f"""
    Here is all the data for you to be able to understand the context: the professors, the time slots and the subjects for the professors
    Professors data:
    {teachers}

    Time slots data: 
    {time_slots}

    Subjects data: 
    {subjects}

    Here are the current add hoc restrictions that are in place for you to have a starting point in the changes that you have to do
    {extra_restrictions}
    
    Your task is to modify the given add hoc restrictions in order to get a result wanted by the user 
    Return in json format only and without any addition comments
    Here is what the user wants to achive as a prompt from the user
    {line}
    """
    print('prompt', prompt)
    client = OpenAI(api_key = "")


    completion = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type" : "json_object"},
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return json.loads(completion.choices[0].message.content) 
    # You could add other patterns here for different restriction types

def rerun_scheduling():
    """
    Clears existing schedules and re-runs the backtracking with updated restrictions.
    """
    global best_timetable, current_timetable, teacher_schedule
    global group_schedule, room_schedule, daily_teacher_hours, transformed_timetable

    # Clear existing global structures
    current_timetable = {}
    teacher_schedule = {}
    group_schedule = {}
    room_schedule = {}
    daily_teacher_hours = {}
    best_timetable = None

    # Re-run backtracking
    backtracking(0)
    # Re-transform
    transformed_timetable = transform_data(best_timetable)
    print("Re-run scheduling complete! Refresh your browser to see updates.")

def console_input_thread():
    global extra_restrictions
    while True:
        line = input("\nEnter new restriction (or press Ctrl+C to quit): ")
        if not line.strip():
            continue
        updated_restrictions = parse_prompt_and_add_restrictions(line, extra_restrictions)
        extra_restrictions = copy.deepcopy(updated_restrictions)
        rerun_scheduling()

# Start a daemon thread to listen for new console input
threading.Thread(target=console_input_thread, daemon=True).start()

# ------------------------------------------------------------------------------------
# Run the Flask app
# ------------------------------------------------------------------------------------
app.run(debug=False,use_reloader=False)
