#!/bin/bash
# Experiment(s)
# Note: don't forget to modify pltpten_time_series.py's "file_list"
expts=""  
expts="$expts enkfrrfs_a_na"
expts="$expts rrfs_a_na"
#expts="$expts enkfrrfs_v0.7.5"
#expts="$expts rrfs_v0.7.5"

# Hour in the log file to get ptend
hours=""
hours="$hours 0.020" # 72s
hours="$hours 1.000" #  1h

n_cyc=336


for hour in $hours; do
for expt in $expts; do

tail -n $n_cyc ./txt/${expt}_${hour}h.txt > ${expt}_${hour}h.txt


done
done
