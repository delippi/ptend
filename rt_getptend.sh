#!/bin/bash

# Summary:
# This script is used to read the forecast log files for "mean abs pgr change"
# and then create/append that information to a text file. At the end of this
# script, pltpten_time_series.py is then called to create the ptend plots.
# Finally, the figure is uploaded to RZDM.

START=$(date +%s)
############### USER INPUT ##################
# Experiment(s)
# Note: don't forget to modify pltpten_time_series.py's "file_list"
expts=""
#expts="$expts enkfrrfs_a_na"
#expts="$expts rrfs_a_na"
#expts="$expts enkfrrfs_v0.8.5"
#expts="$expts rrfs_v0.8.5"

expts="$expts enkfrrfs_v1.0"
expts="$expts rrfs_v1.0"

# Datapath
datapath="/lfs/h2/emc/ptmp/emc.lam/rrfs/" #na/logs/"
datapath="/lfs/h3/emc/lam/noscrub/ecflow/ptmp/emc.lam/ecflow_rrfs/para/output/prod/today"

# Hour in the log file to get ptend
hours=""
hours="$hours 0.020" # 72s
hours="$hours 1.000" #  1h

# Path to  pltpten_time_series.py
scriptpath="/lfs/h2/emc/da/noscrub/donald.e.lippi/rrfs_mon/ptend_48h/"

# Date range for plotting
# Running hourly, just regenerate the past 48 hours of data
date1=$(date --date "48 hour ago" "+%Y%m%d%H")
date2=$(date --date "0 hour ago" "+%Y%m%d%H") # 0-2h+ data likely won't be available.

missing_value="-1.0"
############END USER INPUT ##################

cd $scriptpath
for hour in $hours; do
for expt in $expts; do

  # Get first four characters of experiment name. Need to know if EnVar (rrfs) or EnKF (enkf).
  first_four="${expt:0:4}"
  echo $expt $hour
  date=$date1

  # FOR ENVAR
  if [[ $first_four == "rrfs" ]]; then
    while [[ $date -le $date2 ]]; do
      pdy=`echo $date | cut -c 1-8`
      cyc=`echo $date | cut -c 9-10`
      pstend_ensmean=0
      version=`echo "$expt" | grep -oP "(?<=rrfs_).*"`
      if [[ $version == "a_na" ]]; then
        logfile=`ls ${datapath}/na/logs/rrfs.${pdy}/${cyc}/run_fcst_prod*${date}.log`
      elif [[ $version == "v1.0" ]]; then
        logfile=`ls ${datapath}/${pdy}${cyc}/rrfs_det*forecast*${cyc}.* | grep -v spinup`
      else
        logfile=`ls ${datapath}/$version/logs/rrfs.${pdy}/${cyc}/run_fcst_prod*${date}.log`
      fi
      if [[ -f ${logfile} ]]; then
        pstend=`grep ' mean abs pgr change' ${logfile} | grep "hour     $hour" | awk '{print $10 }'`
      else
        pstend=$missing_value
      fi
      pstend_ensmean=$pstend
      if [[ $date -eq $date1 ]]; then
        echo "$date $pstend_ensmean" > ./${expt}_${hour}h.txt
      else
        echo "$date $pstend_ensmean" >> ./${expt}_${hour}h.txt
      fi
      echo "$date $pstend_ensmean"
      date=`incdate $date 1`
    done #dates
    echo ""

  # FOR ENKF
  elif [[ $first_four == "enkf" ]]; then
    nanals=30
    while [[ $date -le $date2 ]]; do
      pdy=`echo $date | cut -c 1-8`
      cyc=`echo $date | cut -c 9-10`
      nmem=1
      count=0
      pstend_ensmean=0
      while [ $nmem -le $nanals ]; do
        memid=mem`printf %03i $nmem`
        version=`echo "$expt" | grep -oP "(?<=enkfrrfs_).*"`
        if [[ $version == "a_na" ]]; then
          logfile=`ls ${datapath}/na/logs/enkfrrfs.${pdy}/${cyc}/run_fcst_prod*${memid}_${date}.log`
        elif [[ $version == "v1.0" ]]; then
          logfile=`ls ${datapath}/${pdy}${cyc}/rrfs_enkf*forecast*${memid}_${cyc}.* | grep -v ensinit`
        else
          logfile=`ls ${datapath}/$version/logs/enkfrrfs.${pdy}/${cyc}/run_fcst_prod*${memid}_${date}.log`
        fi
        if [[ -f ${logfile} ]]; then
          pstend=`grep ' mean abs pgr change' ${logfile} | grep "hour     $hour" | awk '{print $10 }'`
          # one method for calculating the mean -- only works if all 30 members present.
          #pstend_ensmean=`python -c "print(${pstend_ensmean}+${pstend}/${nanals}.)"`
          # another (better) method for calculating the mean -- works even when all 30 members aren't present.
          count=`python -c "print(${count}+1)"`
          pstend_ensmean=`python -c "print( (${pstend}+${pstend_ensmean}*(${count}-1))/${count}. )"`
        fi
        nmem=$[$nmem+1]
      done #nanals
      if [[ "$pstend_ensmean" == "0" ]]; then
        pstend_ensmean=$missing_value
      fi
      if [[ $date -le $date1 ]]; then
        echo "$date $pstend_ensmean" > ./${expt}_${hour}h.txt
      else
        echo "$date $pstend_ensmean" >> ./${expt}_${hour}h.txt
      fi
      echo "$expt $hour $date $pstend_ensmean"
      date=`incdate $date 1`
    done #dates
    echo ""
  fi

done #expts
done # hours

machine=`hostname | cut -c 1`
if [[ $machine == "c" || $machine == "d" ]]; then
    py=/apps/spack/python/3.8.6/intel/19.1.3.304/pjn2nzkjvqgmjw4hmyz43v5x4jbxjzpk/bin/python
    export incdate=/u/donald.e.lippi/bin/incdate
fi

cd $scriptpath
$py $scriptpath/pltpten_time_series.py

echo "Done making figs. Now upload to rzdm..."

END=$(date +%s)
DIFF=$((END - START))
echo "Time taken to run the code: $DIFF seconds"

# upload to rzdm
ssh-keygen -R emcrzdm.ncep.noaa.gov -f /u/donald.e.lippi/.ssh/known_hosts
rsync -a * donald.lippi@emcrzdm.ncep.noaa.gov:/home/www/emc/htdocs/mmb/dlippi/rrfs_a/ptend/.

echo "Done uploading."
