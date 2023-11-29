#!/bin/bash

# Summary:
# This script is used to read the forecast log files for "mean abs pgr change"
# and then create/append that information to a text file. At the end of this
# script, pltpten_time_series.py is then called to create the ptend plots.
# Finally, the figure is uploaded to RZDM.

############### USER INPUT ##################
# Experiment(s)
# Note: don't forget to modify pltpten_time_series.py's "file_list"
expts=""
#expts="$expts rrfs_conus_enkf_GDASENKF"
#expts="$expts rrfs_conus_enkf_GDASENKF_blending_960"
expts="$expts enkfrrfs_a_na"
expts="$expts rrfs_a_na"
expts="$expts enkfrrfs_v0.7.5"
expts="$expts rrfs_v0.7.5"
#expts="$expts enkfrrfs_v0.7.1"
#expts="$expts rrfs_v0.7.1"

# Datapath
datapath="/lfs/h2/emc/ptmp/emc.lam/rrfs/" #na/logs/"

# Hour in the log file to get ptend
hours=""
hours="$hours 0.020" # 72s
hours="$hours 1.000" #  1h

# Path to  pltpten_time_series.py
scriptpath="/lfs/h2/emc/da/noscrub/donald.e.lippi/rrfs_mon/ptend/"

# Date range for plotting
# Run once per day at 00 UTC to get previous 24h
date1=$(date --date "yesterday" "+%Y%m%d"00)
date2=$(date --date "yesterday" "+%Y%m%d"23)
date1=2023112415
date2=2023112623
#date1=2023091200
#date2=2023091223

missing_value="-1.0"
n_cyc=336 #24*14=336 (or two weeks worth of data to show)
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
      #logfile=`ls ${datapath}/rrfs.${pdy}/${cyc}/run_fcst_prod*${date}.log`
      version=`echo "$expt" | grep -oP "(?<=rrfs_).*"`
      if [[ $version == "a_na" ]]; then
        logfile=`ls ${datapath}/na/logs/rrfs.${pdy}/${cyc}/run_fcst_prod*${date}.log`
      else
        logfile=`ls ${datapath}/$version/logs/rrfs.${pdy}/${cyc}/run_fcst_prod*${date}.log`
      fi
      if [[ -f ${logfile} ]]; then
        pstend=`grep ' mean abs pgr change' ${logfile} | grep "hour     $hour" | awk '{print $10 }'`
      else
        pstend=$missing_value
      fi
      pstend_ensmean=$pstend
      echo "$date $pstend_ensmean" >> ./txt/${expt}_${hour}h.txt
      echo "$date $pstend_ensmean"
      date=`incdate $date 1`
    done #dates

    # From the main text file, only grab the latest n_cyc's... usually 336 (or two weeks).
    tail -n $n_cyc ./txt/${expt}_${hour}h.txt > ${expt}_${hour}h.txt
    echo ""

  # FOR ENKF
  elif [[ $first_four == "enkf" ]]; then
    nanals=30
    while [[ $date -le $date2 ]]; do
      pdy=`echo $date | cut -c 1-8`
      cyc=`echo $date | cut -c 9-10`
      nmem=1
      pstend_ensmean=0
      while [ $nmem -le $nanals ]; do
        memid=mem`printf %04i $nmem`
        #logfile=`ls ${datapath}/enkfrrfs.${pdy}/${cyc}/run_fcst_prod*${memid}_${date}.log`
        version=`echo "$expt" | grep -oP "(?<=enkfrrfs_).*"`
        if [[ $version == "a_na" ]]; then
          logfile=`ls ${datapath}/na/logs/enkfrrfs.${pdy}/${cyc}/run_fcst_prod*${memid}_${date}.log`
        else
          logfile=`ls ${datapath}/$version/logs/enkfrrfs.${pdy}/${cyc}/run_fcst_prod*${memid}_${date}.log`
        fi
        if [[ -f ${logfile} ]]; then
          pstend=`grep ' mean abs pgr change' ${logfile} | grep "hour     $hour" | awk '{print $10 }'`
          pstend_ensmean=`python -c "print(${pstend_ensmean}+${pstend}/${nanals}.)"`
        else
          pstend=$missing_value
          pstend_ensmean=$missing_value
        fi
        nmem=$[$nmem+1]
      done #nanals
        echo "$date $pstend_ensmean" >> ./txt/${expt}_${hour}h.txt
      echo "$date $pstend_ensmean"
      date=`incdate $date 1`
    done #dates

    # From the main text file, only grab the latest n_cyc's... usually 336 (or two weeks).
    tail -n $n_cyc ./txt/${expt}_${hour}h.txt > ${expt}_${hour}h.txt
    echo ""
  fi

done #expts
done # hours

machine=`hostname | cut -c 1`
if [[ $machine == "c" || $machine == "d" ]]; then
    py=/apps/spack/python/3.8.6/intel/19.1.3.304/pjn2nzkjvqgmjw4hmyz43v5x4jbxjzpk/bin/python
    export incdate=/u/donald.e.lippi/bin/incdate
fi

exit
#figdir="/lfs/h2/emc/ptmp/donald.e.lippi/rrfs_a_ptend/figs/"
#mkdir -p $figdir
cd $scriptpath
mkdir -p figs
$py $scriptpath/pltpten_time_series.py
cp ptend_time_series.png figs/.

echo "Done making figs. Now upload to rzdm..."

exit
# upload to rzdm
cd /lfs/h2/emc/da/noscrub/donald.e.lippi/rrfs_mon/ptend/figs
ssh-keygen -R emcrzdm.ncep.noaa.gov -f /u/donald.e.lippi/.ssh/known_hosts
rsync -a * donald.lippi@emcrzdm.ncep.noaa.gov:/home/www/emc/htdocs/mmb/dlippi/rrfs_a/ptend/.

echo "Done uploading."
