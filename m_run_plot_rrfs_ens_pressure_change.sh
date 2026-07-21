#!/bin/bash

set -u
set -o pipefail

cdate="$(date -d yesterday +%Y%m%d)"
cdate="$(date -d today +%Y%m%d)"
#cdate=20260711

workdir=/lfs/h2/emc/ptmp/donald.e.lippi/rrfs_ptend
dest=/lfs/h2/emc/da/noscrub/donald.e.lippi/rrfs_mon/ptend

threshold_low=20
threshold_high=30

# Override this by exporting ALERT_EMAIL before running the script.
alert_email="${ALERT_EMAIL:-donald.e.lippi@noaa.gov}"

run_dir="${workdir}/rrfs_ens_pressure_change_${cdate}"
alert_file="${run_dir}/rrfs_ens_pressure_change_${cdate}_alert.txt"
email_sent_marker="${run_dir}/.pressure_alert_email_sent"

mkdir -p "${workdir}"
cd "${workdir}" || exit 1

# Remove an old alert summary before processing. The Python script will create
# a new one only when at least one value reaches the lower threshold.
rm -f "${alert_file}"

python "${dest}/plot_rrfs_ens_pressure_change.py" \
    "${cdate}" \
    --attempt-policy all \
    --threshold-low "${threshold_low}" \
    --threshold-high "${threshold_high}" \
    --alert-file "${alert_file}"

python_status=$?

if [[ ${python_status} -ne 0 ]]; then
    echo "ERROR: Pressure-change plotting failed with status ${python_status}."
    exit "${python_status}"
fi

date_string="${cdate}_"

cd "${run_dir}" || exit 1

for f in rrfs_ens_pressure_change_"${cdate}"_all_attempts_*.png; do
    # Leave the loop cleanly if no PNG files matched.
    [[ -e "${f}" ]] || continue

    new_name="${f/${date_string}/}"
    cp -p "${f}" "${dest}/today_${new_name}"
done

# Send one email per date when the lower threshold was reached.
if [[ -s "${alert_file}" && ! -e "${email_sent_marker}" ]]; then
    email_subject="[RRFS pressure alert] ${cdate}: >= ${threshold_low} hPa"

    {
        cat "${alert_file}"
        printf "\n"
        printf "Run host: %s\n" "$(hostname)"
        printf "Plot directory: %s\n" "${dest}"
    } > "${run_dir}/email_body.txt"

    email_sent=false

    if command -v mailx >/dev/null 2>&1; then
        if mailx \
            -s "${email_subject}" \
            "${alert_email}" \
            < "${run_dir}/email_body.txt"; then
            email_sent=true
        fi
    elif command -v mail >/dev/null 2>&1; then
        if mail \
            -s "${email_subject}" \
            "${alert_email}" \
            < "${run_dir}/email_body.txt"; then
            email_sent=true
        fi
    else
        echo "ERROR: Neither mailx nor mail is available."
    fi

    if [[ "${email_sent}" == true ]]; then
        touch "${email_sent_marker}"
        echo "Pressure-change alert sent to ${alert_email}."
    else
        echo "ERROR: Pressure-change alert email was not sent."
    fi
elif [[ -e "${email_sent_marker}" ]]; then
    echo "Pressure-change alert was already sent for ${cdate}."
else
    echo "No pressure-change alert for ${cdate}."
fi

