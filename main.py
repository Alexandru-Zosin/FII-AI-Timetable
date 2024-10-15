import json
import copy
fileNames = ['grupe', 'materii', 'profesori', 'sali', 'timp', 'extraRestrictions']
loadedData = {}
# loading the data that we have
for fileName in fileNames:
    with open(f'./data/{fileName}.json', 'r') as file:
        readData = json.load(file)
        loadedData[fileName] = readData

print(loadedData)

# lets generate a timetable using the backtracking 
# the timetable is a object that satisfies the restricitons
bestTimeTable = None
bestTimeTableScore = 0
currentTimetable = {}


def processNextEntry(currentProfesorIndex, currentTimeIndex):
    # here we process the next professor and the next time entry in which we can assign a course
    # logic is if no more time options for current professor
    # we go to the next one only then
    a = 1

def back(profesorIndex, timeIndex):
    if isTimeTableValid() and areHardExtraRestricitonsSatisfied():
        timeTableScore = calculateTimeTableScoreBasedOnSoftRestrictions()
        if timeTableScore > bestTimeTableScore:
            bestTimeTable = copy.deepcopy(bestTimeTableScore)
            bestTimeTableScore = timeTableScore
            return 

    else:
        for grupa in loadedData['grupe']:
            for sala in loadedData['sali']:
                # optimization use only the courses that the professor has
                for materie in loadedData['materie']:
                    addToTimeTable(profesorIndex, timeIndex, grupa, sala, materie)
                    back(processNextEntry(profesorIndex, timeIndex))
                    removeFromTimeTAble(profesorIndex, timeIndex, grupa, sala, materie)


    
    