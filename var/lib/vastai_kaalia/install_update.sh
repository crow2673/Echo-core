#!/bin/bash
pushd . >&/dev/null
CMD="$( cd "$(dirname "$0")" ; pwd -P )/$(basename "$0")"
popd >&/dev/null

export LANG=C.UTF-8
export LC_CTYPE=C.UTF-8
export LC_NUMERIC=C.UTF-8
export LC_TIME=C.UTF-8
export LC_COLLATE=C.UTF-8
export LC_MONETARY=C.UTF-8
export LC_MESSAGES=C.UTF-8
export LC_PAPER=C.UTF-8
export LC_NAME=C.UTF-8
export LC_ADDRESS=C.UTF-8
export LC_TELEPHONE=C.UTF-8
export LC_MEASUREMENT=C.UTF-8
export LC_IDENTIFICATION=C.UTF-8
export LC_ALL=C.UTF-8


function color() {
    if (( ${VAST_DEBUG:-0} >= $2 )); then
        echo -ne '\033['"$1"';01m'
        cat
        echo -ne '\033[m'
    else
        cat >&/dev/null
    fi
}

function log_() {
    tee -a "$LOG" | color 0 "$1"
}
function red() { log_ 31 -1; }
function green() { log_ 32 "$1"; }
function yellow() { log_ 33 "$1"; }
function blue() { log_ 34 "$1"; }
function log() {
    level="$1"
    shift
    date "+%FT%T%Z $*" | green "$level"
}

if [ "$1" = "setup" ]; then
    DO_INSTALL="y"
    DO_RUN="n"
elif [ "$1" = "run" ]; then
    DO_INSTALL="n"
    DO_RUN="y"
else
    DO_INSTALL="y"
    DO_RUN="y"
fi

if [ "$USER" != "vastai_kaalia" ]; then
   echo "WARNING: not running as vastai_kaalia, running as $USER. waiting 60 seconds to make sure you mean this" 2>&1 | red
   sleep 15
   echo "WARNING: this script should be run as user vastai_kaalia. are you sure you meant to do this?" 2>&1 | red
   sleep 15
   echo "WARNING: press ctrl+c in the next 30 seconds to prevent installing vastai daemon as non-daemon user" 2>&1 | red
   sleep 15
   echo "WARNING: 15 seconds remain" 2>&1 | red
   sleep 15
   echo "WARNING: continuing..." 2>&1 | red
fi

cd ~
if [ "x$UPDATE_SERVER" = "x" ]; then
    UPDATE_SERVER="https://s3.amazonaws.com/public.vast.ai/kaalia/daemons"
fi
if [ "x$VAST_SERVER" = "x" ]; then
    VAST_SERVER="https://elb-internal-nocache.vast.ai"
fi

current_version="299"
dir="$HOME/version_$current_version"
LAUNCHER="$HOME/latest/launch_kaalia.sh"
METRICS_PUSHER_LAUNCHER="$HOME/latest/launch_metrics_pusher.sh"
LAUNCHER_TLS="$HOME/latest/launch_tls.sh"
LAUNCHER_SSH="$HOME/latest/launch_bouncer.sh"
GIT_CURRENT_VERSION="$dir/gitversion"
DAEMON="$HOME/daemon.tar.gz"
LOG="$HOME/update_${current_version}.log"
DATADIR="$HOME/data"
VENV="$HOME/venv"
EXPECTED_HASH="bb35fb9189f62abac98c37102e04365a016edbd535ff809ed6129b16a906fa87"
UPDATE_CRON=/etc/cron.d/vastai_kaalia_update
RESTART_CRON=/etc/cron.d/vastai_restart_everything
SYSTEMD_SERVICE="/etc/systemd/system/vastai.service"
SYSTEMD_TLS_SERVICE="/etc/systemd/system/vastai_tls.service"
SSH_BOUNCE_SERVICE="/etc/systemd/system/vastai_bouncer.service"
METRICS_PUSHER_SERVICE="/etc/systemd/system/vast_metrics.service"


if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
    mkdir -p "$dir.backup"
    cp -r "$dir/"* "$dir.backup"
fi

mkdir -p "$dir"
cd "$dir"

function do_get() {
    if [ "x$PACKAGE_PATH" != "x" ]; then
        return 0
    fi
    rm -f "$DAEMON"
    wget "$UPDATE_SERVER"$(cat ~/.channel 2>/dev/null)"/daemon_$current_version.tar.gz" -O "$DAEMON" || return 1
}
function hash_mismatches() {
    if [ "$EXPECTED_HASH" == "PACKAGE""HASH" ]; then
        return 1
    fi
    if [ "$(sha256sum "$DAEMON" | awk '{print $1}')" = "$EXPECTED_HASH" ]; then
        return 1
    fi
    return 0
}
function file_missing() {
    if [ "$current_version" == "DEV""VERSION" ]; then
        if ! [ -e "${PACKAGE_PATH}.d/install" ]; then
            return 1
        fi
        rm -f "${PACKAGE_PATH}.d/install"
        return 0
    fi
    ! [ -f "$DAEMON" ] || return 1
}
if [ "x$PACKAGE_PATH" != "x" ]; then
    DAEMON="$PACKAGE_PATH"
fi

if [ "$DO_INSTALL" = "y" ]; then
    echo "=> Download update"
    log 0 "=> Download update"
    log 0 "=> DAEMON=$DAEMON, EXPECTED_HASH=$EXPECTED_HASH"
    log 0 "=> UPDATE_SERVER=$UPDATE_SERVER, channel=$(cat ~/.channel 2>/dev/null)"
    if file_missing || hash_mismatches; then
        log 2 "=> update needed, doing download"

        if ! do_get | yellow 2; then
            log 0 "=> ERROR: First download attempt failed (wget returned non-zero)"
        fi
        log 0 "=> After first download - File exists: $([ -f "$DAEMON" ] && echo 'yes' || echo 'no'), size: $([ -f "$DAEMON" ] && stat -f%z "$DAEMON" 2>/dev/null || stat -c%s "$DAEMON" 2>/dev/null || echo 'N/A')"
        log 0 "=> Actual hash: $([ -f "$DAEMON" ] && sha256sum "$DAEMON" | awk '{print $1}' || echo 'FILE_MISSING')"

        if hash_mismatches; then
            log 1 "=> Update failed, deleting package and retrying"
            rm "$DAEMON"
            log 0 "=> Removed file, attempting second download"

            if ! do_get | yellow 2; then
                log 0 "=> ERROR: Second download attempt failed (wget returned non-zero)"
            fi
            log 0 "=> After second download - File exists: $([ -f "$DAEMON" ] && echo 'yes' || echo 'no'), size: $([ -f "$DAEMON" ] && stat -f%z "$DAEMON" 2>/dev/null || stat -c%s "$DAEMON" 2>/dev/null || echo 'N/A')"
            log 0 "=> Actual hash: $([ -f "$DAEMON" ] && sha256sum "$DAEMON" | awk '{print $1}' || echo 'FILE_MISSING')"
        fi
        if hash_mismatches; then
            log 0 "=> Update failed, giving up"
            log 0 "=> EXPECTED: $EXPECTED_HASH"
            log 0 "=> ACTUAL: $([ -f "$DAEMON" ] && sha256sum "$DAEMON" | awk '{print $1}' || echo 'FILE_MISSING')"
            exit
        fi
        log 2 "=> Download succeeded"
    else
        log 0 "Up to date, nothing to do"
        exit
    fi

    backup="$HOME/latest.backup"
    if [ -L "$HOME/latest" ]; then
        log 0 "=> Backup old version"
        mv "$HOME/latest" "$backup"
    fi
    log 0 "Install package"

    log 2 "=> Extract daemon"
    log 0 "=> Current directory: $(pwd)"
    log 0 "=> Extracting from: $DAEMON (size: $([ -f "$DAEMON" ] && stat -f%z "$DAEMON" 2>/dev/null || stat -c%s "$DAEMON" 2>/dev/null || echo 'N/A'))"
    log 0 "=> Files in directory before extraction: $(ls -la)"

    if tar -xf "$DAEMON" 2>&1 | tee -a "$LOG"; then
        log 0 "=> Extraction succeeded"
    else
        log 0 "=> ERROR: Extraction failed with exit code $?"
    fi

    log 0 "=> Files in directory after extraction: $(ls -la)"
    log 0 "=> Count of extracted files: $(find . -type f | wc -l)"

    lnt="$HOME/daemon_${current_version}_lntemp"
    ln -s "$dir" "$lnt" | red
    mv -fT "$lnt" "$HOME/latest" | red


    log 2 "=> Update required packages "
    APT_PACKAGES_INSTALLED="n"
    for x in 0 1 2 3 4 5 6; do
        if ! sudo NEEDRESTART_MODE=a apt-get -qq install -y $(cat "$dir"/apt-packages) > >(yellow 3) 2>&1 ; then
            echo "... apt install failed, waiting a few seconds before trying again ..." | yellow 2
            sleep 5
            continue
        else 
            APT_PACKAGES_INSTALLED="y"
        fi
        break
    done
    if [ $APT_PACKAGES_INSTALLED == "n" ]; then
        log 0 "Could not install necessary apt packages, rolling back!"
        cd "$HOME"
        if [ -L "$backup" ]; then
            mv -fT "$backup" "$HOME/latest"
        fi
        rm -rf "$dir"
        if [ -d "$dir.backup" ]; then
            mv -fT "$dir.backup" $dir
        fi
        exit
    else 
        rm -rf "$dir.backup"
        rm -rf "$backup"
    fi
    if ! [ -d "$VENV" ]; then
        log 2 "=> setup virtualenv"
        virtualenv "$VENV" | yellow 3
    fi
    if [ ! -e data/apt-select-out ]; then
        docker run -it --rm -v /etc,/etc,ro vastai/apt-select  | grep '^1.' | sed 's/^[^ \t]\+[ \t]\+//' > data/apt-select-out
    fi

    mkdir -p "$DATADIR"
    cat <<END > "$HOME/environment"
VAST_SERVER="$VAST_SERVER"
END
    echo "$VAST_SERVER" > "$HOME/vast_server"
    echo "b'85d5d1185d44b103f8f3792343f92f94344d8f6e\n'" > "$GIT_CURRENT_VERSION"

    bash "$dir"/onupdate.sh

    log 2 "=> Save systemd service file"
    if [ -e "$SYSTEMD_TLS_SERVICE" ]; then
      sudo systemctl stop vastai_tls
      sudo systemctl disable vastai_tls
      sudo rm -f "$SYSTEMD_TLS_SERVICE"
    fi
    cat <<END | sudo tee "$SYSTEMD_SERVICE" | yellow 3
[Unit]
Description=Vast.ai Host Daemon
Wants=libvirtd.service docker.service
After=libvirtd.service docker.service

[Service]
ExecStart=$LAUNCHER
Restart=always
User=vastai_kaalia
Group=docker
Environment="LIBVIRT_DEFAULT_URI=qemu:///system"
LimitCORE=2147483648

[Install]
WantedBy=multi-user.target
END
    cat <<END | sudo tee "$SSH_BOUNCE_SERVICE" | yellow 3
[Unit]
Description=Vast.ai Support Daemon

[Service]
ExecStart=$LAUNCHER_SSH
Restart=always
User=vastai_kaalia
Group=docker

[Install]
WantedBy=multi-user.target
END
    cat <<END | sudo tee "$METRICS_PUSHER_SERVICE" | yellow 3
[Unit]
Description=Vast.ai Machine Metrics
Wants=docker.service
After=docker.service

[Service]
ExecStart=$METRICS_PUSHER_LAUNCHER
Restart=always
RestartSec=10
User=vastai_kaalia
Group=docker

[Install]
WantedBy=multi-user.target
END




    if ! [ -e "$UPDATE_CRON" ] ; then
        log 2 "=> Randomize cron time to avoid update stampeding"
        HOSTNAME_HASH="$(( $((16#$(hostname | sha256sum | head -c 8) )) / ( 2 ** 32 / 58 )  ))"

        log 2 "=> Generate cron file for update"
        echo 'SHELL=/bin/bash' | sudo tee $UPDATE_CRON | yellow 3
        echo 'PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin' | sudo tee -a $UPDATE_CRON | yellow 3
        echo "$HOSTNAME_HASH" '* * * * vastai_kaalia' "bash $HOME/update_launcher.sh" |  sudo tee -a $UPDATE_CRON | yellow 3
    fi
    log 0 "=> Update done"
fi

if [ "$DO_RUN" = "y" ]; then
    log 2 "=> Reload systemd config"
    sudo systemctl daemon-reload 2>&1 | red
    log 0 "=> Restart daemon"
    sudo service vastai restart
    sleep 1
    log 2 "=> Enable kaalia to start on boot"
    sudo systemctl enable vastai

    log 0 "=> Restart metrics pusher"
    sudo service vast_metrics restart
    log 2 "=> Enable metrics pusher to start on boot"
    sudo systemctl enable vast_metrics

    log 2 "=> Generate cron file for autorestarting"
    HOSTNAME_HASH="$(( $((16#$(hostname | sha256sum | head -c 8) )) / ( 2 ** 32 / 58 )  ))"
    #H2="$(( ($HOSTNAME_HASH + 15) % 60 ))"
    #H3="$(( ($HOSTNAME_HASH + 30) % 60 ))"
    #H4="$(( ($HOSTNAME_HASH + 45) % 60 ))"
    echo 'SHELL=/bin/bash' | sudo tee $RESTART_CRON | yellow 3
    echo 'PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin' | sudo tee -a $RESTART_CRON | yellow 3
    echo '* * * * * vastai_kaalia' "bash $HOME/latest/restart.sh" |  sudo tee -a $RESTART_CRON | yellow 3
    #echo "$HOSTNAME_HASH" '* * * * vastai_kaalia' "bash $HOME/latest/restart.sh" |  sudo tee -a $RESTART_CRON | yellow 3
    #echo "$H2" '* * * * vastai_kaalia' "bash $HOME/latest/restart.sh" |  sudo tee -a $RESTART_CRON | yellow 3
    #echo "$H3" '* * * * vastai_kaalia' "bash $HOME/latest/restart.sh" |  sudo tee -a $RESTART_CRON | yellow 3
    #echo "$H4" '* * * * vastai_kaalia' "bash $HOME/latest/restart.sh" |  sudo tee -a $RESTART_CRON | yellow 3

    log 0 "=> Launch done"
fi
