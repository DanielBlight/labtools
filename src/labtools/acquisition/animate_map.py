################################
# imports
################################
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.animation as animation
from matplotlib import pyplot as plt
import time as t
import os
import numpy as np
import datetime
import ancFunctions as af
import PLmapFunctions as pf
from labtools.devices.itc4000 import ITC4000
from labtools.devices.labjack_u6 import LabJackU6
from labtools.devices.scanning_mirror import ScanningMirror
from labtools.devices.spad_gate import SPADGate
import pandas as pd
from timeControllerLibrary import timeController
from scipy.interpolate import griddata
import matplotlib
matplotlib.use('Qt5Agg')

################################
# configuration  # CAN CHANGE
################################
outputPath = "C:\\Users\\Legend\\Documents\\Dan\\NiV\\Maps\\Area4\\"
ITC4000_ADDRESS = 'USB0::0x1313::0x804A::M00739898::INSTR'
TIME_TAGGER_IP = "169.254.99.159"
TIME_TAGGER_PORT = 5555

now = datetime.datetime.now()
folderName = now.strftime("%Y-%m-%d-%H.%M")
outputFolder = "".join([outputPath, folderName])
if (os.path.exists(outputFolder) == False):
    os.makedirs(outputFolder)

################################
# instruments
################################
# connect to mirror and SPAD gate (share one U6 connection)
lj = LabJackU6()
mirror = ScanningMirror(lj, dio_pin=2)
spad = SPADGate(lj, pin=0)
spad.open()
# time tagger
integration_time = 120# (ms) CAN CHANGE. 100 gives us decent counts for ErYLF
tc = timeController(ipAddress=TIME_TAGGER_IP, port=TIME_TAGGER_PORT)
tc.set_integration_time_ms(1, integration_time)
tc.set_integration_time_ms(4, integration_time)
########################################################
t.sleep(0.1)
########################################################
#print(f"SPAD integration time = %.3f" % tc.integrationTime1)
# laser
laserCurrent = 0.08  # CAN CHANGE
laser = ITC4000(ITC4000_ADDRESS)
laser.enable(current=laserCurrent)
# stage
anc = af.getANC()
anc.set_voltage(axis=1, voltage=30)  # z
anc.set_voltage(axis=2, voltage=60)  # y
anc.set_voltage(axis=0, voltage=60)  # x
anc.set_frequency(axis='all', freq=50)
anc.set_sensor_voltage(2.048)
xCoord = af.getX(anc) * 1e6  # in micron
yCoord = af.getY(anc) * 1e6
zCoord = af.getZ(anc) * 1e6

################################
# set variables for mapping
################################
# define range of map
xStart,xStop,xNum =-4,4,200 #start and end positions, number of points in x
yStart,yStop,yNum = -1,6,200 # start and end positions, number of points in y
# voltages to set the stage z piezo, changing the focus
focusVoltages = [0,30,60] # CAN CHANGE
# define target co-ordinates for mapping area, this will be an array of shape (xnum*ynum,2)
xVals = np.linspace(xStart, xStop, xNum)
yVals = np.linspace(yStart, yStop, yNum)
xTargets = np.tile(xVals, yNum)
yTargets = np.repeat(yVals, xNum)
targets = np.array([xTargets, yTargets])
targets = targets.T
# np.random.shuffle(targets)
iterations = targets.shape[0]
totaldata = np.zeros(iterations)
notes = '1550-40 in collection path, E5 square, post 500C reanneal.'
################################
# function for animation
################################


def updatePlot(frame_num):
    global map_done
    map_done = False
    # {}
    # measure
    # sleepTime = integration_time * 1.2 + 10
    # t.sleep(sleepTime / 1e3)
    data[frame_num] =  tc.get_counts(4)* (1 / (integration_time * 1e-3))  # counts/sec

    # move mirror
    if frame_num != iterations-1:
        mirror.move(targets[frame_num+1, 0], targets[frame_num+1, 1])
        # add focus change if you want it

    #  Plot
    gridZ = griddata(points, data, (gridX, gridY), method='nearest')
    vmin = np.min(data)
    vmax = np.max(data)
    # if (ii % 10) == 0:
    #     # pf.plotMap_V(x,y,z,max(xNum,yNum),fast=False)
    #     pf.updatePlot(fig, gridX, gridY, gridZ)
    im.set_array(gridZ.ravel())
    im.set_clim(vmin, vmax)

    # Remaining time
    if (frame_num % 50) == 0:
        currentTime = datetime.datetime.now()
        print("Map started at: ", str(startTime).split('.')[0][:-3], "\nEstimated finish time: ",
              str(currentTime + ((currentTime - startTime) * (iterations - frame_num - 1) / (frame_num + 1))).split('.')[0][:-3])

    # need to know when the animation is done so we can start the next one in the loop
    if frame_num == iterations-1:
        map_done = True


################################
# perform map
################################
count = 0
# af.move_to_DC(anc, 1, 30)  #CHANGED
for focusVoltage in focusVoltages:
    map_done = False
    mirror.move(targets[0, 0], targets[0, 1])
    t.sleep(0.1)
    if focusVoltage <= 60:
        af.move_to_DC(anc, 1, focusVoltage)
    else:
        diff = np.abs(focusVoltage - focusVoltages[count - 1])
        af.jogStage(anc, 1, diff, 1)

    t.sleep(1)

    count = count + 1

    ################################
    # initial plot
    ################################
    data = np.zeros(iterations)
    x = targets[:, 0]
    y = targets[:, 1]
    z = data

    # make mesh grid for pcolormesh function and grid the data
    xmin, ymin = np.min(x), np.min(y)
    xmax, ymax = np.max(x), np.max(y)
    gridPoints = max(xNum, yNum) * 1j
    gridX, gridY = np.mgrid[xmin:xmax:gridPoints, ymin:ymax:gridPoints]
    points = np.array([x, y]).T
    gridZ = griddata(points, z, (gridX, gridY), method='nearest')
    fig, ax = plt.subplots()

    # plot
    im = ax.pcolormesh(gridX, gridY, gridZ, cmap='inferno')  # 'inferno')
    # div = make_axes_locatable(ax)
    # cax = div.append_axes('right', '5%', '5%')
    # fixes aspect ratio as laser spot moves less in y than x for same voltage
    ax.set_aspect(0.75)
    cb = fig.colorbar(im, fraction=0.046*0.75, pad=0.04,
                      label='PL Intensity [Counts / sec]')
    ax.set_xlabel('DC offset [V]')
    ax.set_ylabel('DC offset [V]')
    plt.tight_layout()

    # main animation
    startTime = datetime.datetime.now()
    ani = animation.FuncAnimation(fig, updatePlot, frames=iterations,
                                  interval=integration_time * 1.2 + 10, repeat=False, cache_frame_data=False)
    # block=False so execution doesnt wait for the figure to be closed
    plt.show(block=False)
    while map_done is False:
        # this is needed to do sequential animations in a loop. Waits for one animation to finish then closes the figure
        plt.pause(0.5)
    plt.close()

    # return mirror to 0
    mirror.home()

    # add data to summed array
    totaldata = totaldata + data

    # save figures and data
    figureFilename = outputFolder + f"\\Voltages{focusVoltage}V.png"
    x = targets[:, 0]
    y = targets[:, 1]
    z = data
    pf.plotMap_V(x, y, z, max(xNum, yNum), fileName=figureFilename, fast=False)
    plt.close()

    # change the bit in quotes to the name of the figure you want
    figureFilename = outputFolder + f"\\logVoltages{focusVoltage}V.png"
    x = targets[:, 0]
    y = targets[:, 1]
    z = np.log(data)
    pf.plotMap_V(x, y, z, max(xNum, yNum), fileName=figureFilename, fast=False)
    plt.close()

    dataFilename = outputFolder + f"\\data{focusVoltage}V.csv"
    temp = data.reshape(yNum, xNum)
    ind = np.round(yVals, 3)
    col = np.round(xVals, 3)
    df = pd.DataFrame(temp, index=ind, columns=col)
    df.to_csv(dataFilename)


# save total data
# change the bit in quotes to the name of the figure you want
figureFilename = outputFolder + f"\\sumVoltages.png"
x = targets[:, 0]
y = targets[:, 1]
z = totaldata
pf.plotMap_V(x, y, z, max(xNum, yNum), fileName=figureFilename, fast=False)
plt.close()

# change the bit in quotes to the name of the figure you want
figureFilename = outputFolder + f"\\logsumVoltages.png"
x = targets[:, 0]
y = targets[:, 1]
z = np.log(totaldata)
pf.plotMap_V(x, y, z, max(xNum, yNum), fileName=figureFilename, fast=False)
plt.close()

dataFilename = outputFolder + f"\\sumVoltagesData.csv"
temp = totaldata.reshape(yNum, xNum)
ind = np.round(yVals, 3)
col = np.round(xVals, 3)
df = pd.DataFrame(temp, index=ind, columns=col)
#df.to_csv(dataFilename)
# print(anc.get_offset(axis=1))
# af.move_to_DC(anc, 1, 0)
x
# ###############################
# metadata
#################################
# if you want to save any more variables just add their name to the for loop and they'll be saved to the MetaData.txt file
outputFilenameMetaData = outputFolder + "\\MetaData.txt"
with open(outputFilenameMetaData, 'w') as f:
    for ii in ('xStart', 'xStop', 'xNum', 'yStart', 'yStop', 'yNum', 'laserCurrent', 'xCoord', 'yCoord', 'zCoord',
                'integration_time','notes'):
        val = str(locals()[ii])
        f.write(f"{ii} = {val}\n")

################################
# turn off/disconnect instruments
################################
# laser
laser.disable()
laser.close()
# mirror / U6
mirror.home()
spad.close()
lj.close()
# stage
# anc.close()
