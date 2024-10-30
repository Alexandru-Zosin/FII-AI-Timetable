import json
import copy
import fundamentalRestricitons
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

hardRestrictions = []
softRestrictions = []

def addToTimeTable (profesorIndex, timeIndex, grupa, sala, materie):
    if not profesorIndex in currentTimetable:
        currentTimetable[profesorIndex] = {}

    currentTimetable[profesorIndex][timeIndex] = (grupa, sala, materie)

def removeFromTimeTAble(profesorIndex, timeIndex, grupa, sala, materie):
    currentTimetable[profesorIndex].pop(timeIndex)

def isTimeTableValid():
    #in this function we want to test if the fundamental restrictions are validated


def processNextEntry(currentProfesorIndex, currentTimeIndex):
    # here we process the next professor and the next time entry in which we can assign a course
    # logic is if no more time options for current professor
    # we go to the next one only then

    if currentProfesorIndex == len(loadedData['profesori']):
        return (-1, -1)

    if currentTimeIndex == 30: 
        # this means we finished all time slots for current professor 
        # so we move to the next one 
        currentProfesorIndex += 1
        currentTimeIndex = 0

    else:
        currentTimeIndex += 1

    return (currentProfesorIndex, currentTimeIndex)

def back(profesorIndex, timeIndex):
    # this means no more professors
    if profesorIndex == -1 or timeIndex == -1:
        return
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


    
    