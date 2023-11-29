#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Oct 21 09:19:49 2021
"""
import matplotlib
import matplotlib.pyplot as plt
import sys
import numpy as np
import datetime

#Necessary to generate figs when not running an Xserver (e.g. via PBS)
plt.switch_backend('agg')
matplotlib.style.use('ggplot')


sdate = str(sys.argv[1])
edate = str(sys.argv[2])
logs = str(sys.argv[3])+"/rrfs_a_na"
enkfrrfs = "refs"

sdate = datetime.datetime.strptime(sdate, "%Y%m%d%H")
edate = datetime.datetime.strptime(edate, "%Y%m%d%H")
delta = edate - sdate
date_list = [sdate + datetime.timedelta(hours=i) for i in range(0, delta.days * 24 + delta.seconds // 3600 + 1, 6)]
date_list_str = [d.strftime("%Y%m%d%H") for d in date_list]

fnames = []
labels = []
colors = []
length = len(date_list_str)

i = 0
for date in date_list_str:
    pdy=date[0:8]
    cyc=date[8:10]
    #fnames.append(f"{logs}/{enkfrrfs}.{pdy}/{cyc}/run_fcst_prod_c3enkf64_mem0001_{date}.log")
    fnames.append(f"{logs}/{enkfrrfs}.{pdy}/{cyc}/run_fcst_prod_n3enfcst61_mem0001_{date}.log")
    labels.append(f"{date}")
    red = (255 - i*(255//length))/255
    green = 0
    blue = (0 + i*(255//length))/255
    colors.append((red, green, blue))
    i+=1

def isfloat(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

if __name__ == '__main__':

# Start the figure
  fig = plt.figure(figsize=(8, 6))
  mytitle='Mean Absolute Pressure Tendency '
  plt.title(mytitle)
  plt.ylabel('hPa/hr')
  plt.xlabel('Timestep (hours)')
  nhr=4800

  for fname,label,color in zip(fnames,labels,colors):
      myptend=[]
      keystrings=['At forecast hour','mean abs pgr change is','hPa/hr']
      print(fname)
      with open(fname, 'r') as f:
          for line in f:
              if any(x in line.strip() for x in keystrings):
                  myptend.append([float(s) for s in line.split() if isfloat(s)])

      dat=np.array(myptend)

      print(color)
      plt.plot(dat[0:nhr,0],dat[0:nhr,1],color=color,label=label)

  plt.legend()
  plt.savefig(f'./ptend.png',bbox_inches='tight')
