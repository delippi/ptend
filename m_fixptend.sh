#!/bin/bash

# Experiment
expts=""
#expts="$expts rrfs_conus_enkf_GDASENKF"
#expts="$expts rrfs_conus_enkf_GDASENKF_blending_960"
expts="$expts enkfrrfs_a_na"
expts="$expts rrfs_a_na"

# Datapath
datapath="/lfs/h2/emc/ptmp/emc.lam/rrfs/na/logs/"

# Hour in the log file to get ptend
hours=""
hours="$hours 0.020"
hours="$hours 1.000"

scriptpath="/lfs/h2/emc/da/noscrub/donald.e.lippi/rrfs_mon/ptend/"

# Date range for plotting
# Run at 00 UTC
#date1=$(date --date "yesterday" "+%Y%m%d"00)
#date2=$(date --date "yesterday" "+%Y%m%d"23)
date1=2023091023

date2=$date1

missing_value="-1.0"
n_cyc=336 #24*14=336 (or two weeks worth of data to show)
############END USER INPUT ##################

mkdir -p fixed
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
      logfile=`ls ${datapath}/rrfs.${pdy}/${cyc}/run_fcst_prod*${date}.log`
      if [[ -f ${logfile} ]]; then
        pstend=`grep ' mean abs pgr change' ${logfile} | grep "hour     $hour" | awk '{print $10 }'`
      else
        pstend=$missing_value
      fi
      pstend_ensmean=$pstend
      if [[ $pstend_ensmean -le 0 ]]; then
         echo "$logfile"
         exit
      fi
      echo "$date $pstend_ensmean" >> ./fixed/${expt}_${hour}h.txt
      echo "$date $pstend_ensmean"
      date=`incdate $date 1`
    done #dates 

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
        #if [[ $cyc == "18" || $cyc == "06"  ]]; then
        #  logfile=`ls ${datapath}/enkfrrfs.${pdy}/${cyc}/run_fcst_spinup*${memid}_${date}.log`
        #else
        logfile=`ls ${datapath}/enkfrrfs.${pdy}/${cyc}/run_fcst_prod*${memid}_${date}.log`
        #fi
        if [[ -f ${logfile} ]]; then
          pstend=`grep ' mean abs pgr change' ${logfile} | grep "hour     $hour" | awk '{print $10 }'`
          pstend_ensmean=`python -c "print(${pstend_ensmean}+${pstend}/${nanals}.)"`
        else
          pstend=$missing_value
          pstend_ensmean=$missing_value
        fi
        nmem=$[$nmem+1]
      done #nanals
        echo "$date $pstend_ensmean" >> ./fixed/${expt}_${hour}h.txt
      echo "$date $pstend_ensmean"
      date=`incdate $date 1`
    done #dates
  fi

done #expts
done # hours

exit
machine=`hostname | cut -c 1`
if [[ $machine == "c" || $machine == "d" ]]; then
    py=/apps/spack/python/3.8.6/intel/19.1.3.304/pjn2nzkjvqgmjw4hmyz43v5x4jbxjzpk/bin/python
    export incdate=/u/donald.e.lippi/bin/incdate
fi

#figdir="/lfs/h2/emc/ptmp/donald.e.lippi/rrfs_a_ptend/figs/"
#mkdir -p $figdir
cd $scriptpath
mkdir -p figs
$py $scriptpath/pltpten_time_series.py
cp ptend_time_series.png figs/.

echo "Done."

exit
# upload to rzdm
cd /lfs/h2/emc/da/noscrub/donald.e.lippi/rrfs_mon/ptend/figs
ssh-keygen -R emcrzdm.ncep.noaa.gov -f /u/donald.e.lippi/.ssh/known_hosts
rsync -a * donald.lippi@emcrzdm.ncep.noaa.gov:/home/www/emc/htdocs/mmb/dlippi/rrfs_a/ptend/.
