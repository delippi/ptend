import matplotlib
import matplotlib.pyplot as plt
import datetime
import glob
import numpy as np
import matplotlib.dates as mdates

#Necessary to generate figs when not running an Xserver (e.g. via PBS)
plt.switch_backend('agg')
matplotlib.style.use('ggplot')

# Set the figure size
fig = plt.figure(figsize=(12, 7))

# Get a list of all text files in the directory
#file_list = glob.glob('*.txt')
file_list = [
"enkfrrfs_a_na_1.000h.txt", "rrfs_a_na_1.000h.txt", "enkfrrfs_a_na_0.020h.txt", "rrfs_a_na_0.020h.txt",
"enkfrrfs_v0.7.9_1.000h.txt", "rrfs_v0.7.9_1.000h.txt", "enkfrrfs_v0.7.9_0.020h.txt", "rrfs_v0.7.9_0.020h.txt",
"enkfrrfs_v0.8.1_1.000h.txt", "rrfs_v0.8.1_1.000h.txt", "enkfrrfs_v0.8.1_0.020h.txt", "rrfs_v0.8.1_0.020h.txt",
#"enkfrrfs_v0.7.5_1.000h.txt", "rrfs_v0.7.5_1.000h.txt", "enkfrrfs_v0.7.5_0.020h.txt", "rrfs_v0.7.5_0.020h.txt",
#"enkfrrfs_v0.7.1_1.000h.txt", "rrfs_v0.7.1_1.000h.txt", "enkfrrfs_v0.7.1_0.020h.txt", "rrfs_v0.7.1_0.020h.txt",
]

# Set colors
#colors = ['k', 'tab:blue', 'k', 'tab:blue', 'gray', 'tab:red', 'gray', 'tab:red']
colors = ['k',       'tab:blue',   'k',       'tab:blue',
          'gray',    'tab:red',    'gray',    'tab:red',
          'goldenrod', 'tab:green', 'goldenrod', 'tab:green',
         ]

linestyles = ['-', '-', '--', '--',
              '-', '-', '--', '--',
              '-', '-', '--', '--']

import pdb
min_timestamp = datetime.datetime.max
max_timestamp = datetime.datetime.min

# Iterate over each file
for file_name in file_list:
    i = file_list.index(file_name)
    # Read the text file
    with open(file_name, 'r') as f:
        lines = f.readlines()

    # Extract the data from the lines
    timestamps = []
    values = []
    for line in lines:
        parts = line.split()
        timestamp = datetime.datetime.strptime(parts[0], "%Y%m%d%H")
        try:
            value = float(parts[1])
        except IndexError:
            print(f"Index Error: let's see where it went wrong...")
            print(f"    {file_name}: {line}")
            value = -1.0  # missing
        if(value >=0):
            timestamps.append(timestamp)
            values.append(value)

        # Update min and max timestamps
        if timestamp < min_timestamp:
            min_timestamp = timestamp
        if timestamp > max_timestamp:
            max_timestamp = timestamp

    # Plot the time series
    values = np.array(values)
    label = file_name.replace('.txt','')  # Remove the '.txt' extension from the label.
    label = label.replace('_1.000h', ' (1h)')
    label = label.replace('_0.020h', ' (72s)')
    #values[values < 0] = np.nan
    plt.plot(timestamps, values, label=label, linestyle=linestyles[i], color=colors[i], marker='o', ms="4")


# Set labels and title and axis limits
plt.xlabel('Date')
plt.ylabel('hPa/h')
plt.title('Absolute Surface Pressure Tendency')
plt.ylim(bottom=0, top=12)

# Set the x-axis tick labels to show only at the 00 hour and set minor ticks
plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=1))
plt.gca().xaxis.set_minor_locator(mdates.HourLocator(byhour=[6,12,18]))
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H'))

# Set the x-axis ticks every 24 hours
#plt.xticks(np.arange(min(timestamps), max(timestamps), datetime.timedelta(hours=24)), rotation=90)
plt.xticks(np.arange(min_timestamp, max_timestamp, datetime.timedelta(hours=24)), rotation=90)

# Add legend
plt.legend(ncol=int(len(file_list)/4))

# Display the plot
plt.savefig("./ptend_time_series.png",bbox_inches="tight")
