# Installazione Arch Linux su ASUS ProArt PX13

Questa guida descrive l'installazione di Arch Linux sul PX13 con disco `/dev/nvme0n1`, LUKS2, LVM, Btrfs, ibernazione e `systemd-boot`.

I valori di riferimento sono:

- Hostname: `hero`
- Utente principale: `sid`
- Password/passphrase temporanee: `install`
- Timezone: `Europe/Rome`
- Lingua applicativi: inglese, con convenzioni numeriche/valuta italiane
- Layout tastiera per LUKS: italiano

## 1. Boot da Live ISO

La ISO Arch utilizzata (archlinux-2026.06.01-x86_64.iso) ha bisogno del parmetro kernel `nomodeset` per arrivare al login. Tale parametro serve solo nella live, non sarà usato per il kernel installato.

Imposta il layout tastiera italiano nella live ISO. È importante perché la passphrase LUKS viene digitata con questo layout.

```sh
loadkeys it
```

Carica un font più grande e leggibile nella console della live ISO. Non è necessario installarlo nel sistema finale.

```sh
setfont ter-132b
```

Imposta il fuso orario della live ISO.

```sh
timedatectl set-timezone Europe/Rome
```

Avvia il server SSH sulla live ISO per amministrare il portatile da un'altra macchina.

```sh
systemctl start sshd
```

Imposta la password temporanea di root nella live ISO. In questa guida la password temporanea è `install`.

```sh
passwd
```

Crea o riusa una sessione tmux chiamata `install` nella live ISO. In questa fase è utile perché l'installazione avviene via SSH e tmux evita di perdere il lavoro se cade la connessione.

```sh
tmux new -A -s install
```

## 2. Connessione remota

Entra nella live ISO via SSH. L'indirizzo può cambiare: verifica quello assegnato al portatile.

```sh
ssh root@192.168.3.161
```

Agganciati alla sessione tmux creata sulla live ISO. I comandi distruttivi e l'installazione vanno eseguiti dentro questa sessione.

```sh
tmux attach -t install
```

## 3. Verifiche preliminari

Verifica che la ISO sia avviata in modalità UEFI. `systemd-boot` richiede un avvio UEFI.

```sh
test -d /sys/firmware/efi && echo UEFI=yes || echo UEFI=no
```

Controlla che il disco target sia quello corretto. Sul PX13 documentato qui è il Sandisk NVMe da circa 1.9T.

```sh
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL /dev/nvme0n1
```

Verifica che la rete funzioni prima di scaricare i pacchetti.

```sh
ping -c 2 archlinux.org
```

Controlla sincronizzazione oraria e timezone. Un orologio errato può creare problemi con firme e TLS.

```sh
timedatectl
```

## 4. Pulizia disco e partizionamento

Attenzione: questi comandi cancellano `/dev/nvme0n1`.

Definisce variabili per ridurre errori nei comandi successivi. Le opzioni Btrfs sono quelle usate nell'installazione.

```sh
DISK=/dev/nvme0n1
ESP=${DISK}p1
CRYPT=${DISK}p2
BTRFS_OPTS=rw,noatime,compress=zstd:3,ssd,discard=async,space_cache=v2
```

Spegne swap, smonta eventuali mount precedenti e chiude vecchi LVM/LUKS se presenti.

```sh
swapoff -a
umount -R /mnt
vgchange -an vg0
cryptsetup close cryptroot
```

Cancella vecchie tabelle partizioni e metadati GPT/MBR dal disco target.

```sh
sgdisk --zap-all "$DISK"
```

Crea una ESP da 1GiB e una seconda partizione per il container LUKS sul resto del disco.

```sh
sgdisk -n 1:0:+1GiB -t 1:ef00 -c 1:EFI -n 2:0:0 -t 2:8309 -c 2:cryptroot "$DISK"
```

Chiede al kernel di rileggere la tabella partizioni e attende che i device siano pronti.

```sh
partprobe "$DISK"
udevadm settle
```

Formatta la partizione EFI in FAT32, formato richiesto dal firmware UEFI.

```sh
mkfs.fat -F 32 -n EFI "$ESP"
```

## 5. LUKS, LVM, swap e Btrfs

Crea il container LUKS2 sulla seconda partizione. Qui `install` è una passphrase temporanea da cambiare subito dopo il primo boot.

```sh
printf 'install' | cryptsetup luksFormat --type luks2 --batch-mode --key-file - "$CRYPT"
```

Apre il container come `/dev/mapper/cryptroot` e abilita discard/TRIM attraverso LUKS.

```sh
printf 'install' | cryptsetup open --allow-discards --key-file - "$CRYPT" cryptroot
```

Inizializza LVM dentro LUKS e crea il volume group `vg0`.

```sh
pvcreate /dev/mapper/cryptroot
vgcreate vg0 /dev/mapper/cryptroot
```

Crea una swap cifrata da 160GiB per supportare l'ibernazione e assegna il resto al volume root.

```sh
lvcreate -L 160G -n swap vg0
lvcreate -l 100%FREE -n root vg0
```

Formatta il logical volume swap.

```sh
mkswap -L swap /dev/vg0/swap
```

Formatta il logical volume root in Btrfs.

```sh
mkfs.btrfs -f -L root /dev/vg0/root
```

Monta temporaneamente il filesystem Btrfs principale per creare i subvolumi.

```sh
mount /dev/vg0/root /mnt
```

Crea i subvolumi per root, home, modelli LLM, cache pacman, log e snapshot.

```sh
btrfs subvolume create /mnt/@
btrfs subvolume create /mnt/@home
btrfs subvolume create /mnt/@models
btrfs subvolume create /mnt/@pkg
btrfs subvolume create /mnt/@varlog
btrfs subvolume create /mnt/@snapshot
```

Smonta il top-level Btrfs per rimontare i subvolumi nei punti definitivi.

```sh
umount /mnt
```

Monta il subvolume root e crea le directory per gli altri mount.

```sh
mount -o "$BTRFS_OPTS,subvol=@" /dev/vg0/root /mnt
mkdir -p /mnt/home /mnt/srv/models /mnt/var/cache/pacman/pkg /mnt/var/log /mnt/.snapshots /mnt/boot
```

Monta tutti i subvolumi Btrfs con compressione Zstd, noatime e discard asincrono.

```sh
mount -o "$BTRFS_OPTS,subvol=@home" /dev/vg0/root /mnt/home
mount -o "$BTRFS_OPTS,subvol=@models" /dev/vg0/root /mnt/srv/models
mount -o "$BTRFS_OPTS,subvol=@pkg" /dev/vg0/root /mnt/var/cache/pacman/pkg
mount -o "$BTRFS_OPTS,subvol=@varlog" /dev/vg0/root /mnt/var/log
mount -o "$BTRFS_OPTS,subvol=@snapshot" /dev/vg0/root /mnt/.snapshots
```

Monta la ESP in `/boot`, dove saranno messi kernel, initramfs e systemd-boot.

```sh
mount "$ESP" /mnt/boot
```

Attiva la swap cifrata per l'ambiente live e per generare correttamente `fstab`.

```sh
swapon /dev/vg0/swap
```

## 6. Installazione pacchetti base

Aggiorna prima il keyring Arch per ridurre il rischio di errori di firma durante `pacstrap`.

```sh
pacman -Sy --noconfirm archlinux-keyring
```

Installa il sistema base, entrambi i kernel, firmware, microcode AMD, strumenti storage/boot, rete, SSH, sudo, `inetutils` per comandi come `hostname` e userspace grafico AMD/Mesa. `mesa-vdpau` era stato considerato ma non era disponibile nel repository usato.

```sh
pacstrap -K /mnt base base-devel linux linux-lts linux-firmware linux-headers linux-lts-headers amd-ucode btrfs-progs lvm2 cryptsetup dosfstools efibootmgr networkmanager openssh sudo inetutils vim nano git bash-completion man-db man-pages texinfo sof-firmware mesa vulkan-radeon libva-mesa-driver iwd usbutils pciutils wget amd-debug-tools ethtool
```

## 7. Configurazione sistema

Salva gli UUID necessari per la riga kernel: LUKS per sbloccare root e swap per il resume da ibernazione.

```sh
CRYPT_UUID=$(blkid -s UUID -o value /dev/nvme0n1p2)
SWAP_UUID=$(blkid -s UUID -o value /dev/vg0/swap)
```

Genera `fstab` usando UUID stabili invece di nomi device variabili.

```sh
genfstab -U /mnt > /mnt/etc/fstab
```

Configura timezone del sistema installato e sincronizza l'orologio hardware.

```sh
ln -sf /usr/share/zoneinfo/Europe/Rome /mnt/etc/localtime
arch-chroot /mnt hwclock --systohc
```

Abilita locale inglese e italiana, poi genera i file locale.

```sh
sed -i 's/^#\(en_US.UTF-8 UTF-8\)/\1/' /mnt/etc/locale.gen
sed -i 's/^#\(it_IT.UTF-8 UTF-8\)/\1/' /mnt/etc/locale.gen
arch-chroot /mnt locale-gen
```

Mantiene applicativi e sistema in inglese, ma usa convenzioni italiane per numeri, date, valuta, carta e unità di misura.

```sh
cat > /mnt/etc/locale.conf <<'EOF'
LANG=en_US.UTF-8
LC_NUMERIC=it_IT.UTF-8
LC_TIME=it_IT.UTF-8
LC_MONETARY=it_IT.UTF-8
LC_PAPER=it_IT.UTF-8
LC_MEASUREMENT=it_IT.UTF-8
EOF
```

Imposta il layout console italiano nel sistema installato. Non viene impostato `FONT=ter-132b` perché non è disponibile di default nel sistema installato.

```sh
cat > /mnt/etc/vconsole.conf <<'EOF'
KEYMAP=it
EOF
```

Imposta l'hostname del sistema.

```sh
printf 'hero\n' > /mnt/etc/hostname
```

Configura la risoluzione locale di hostname e localhost.

```sh
cat > /mnt/etc/hosts <<'EOF'
127.0.0.1 localhost
::1 localhost
127.0.1.1 hero.localdomain hero
EOF
```

Crea il gruppo `sudo` se manca e l'utente principale `sid` con home directory e shell Bash.

```sh
arch-chroot /mnt groupadd -f sudo
arch-chroot /mnt useradd -m -G sudo -s /bin/bash sid
```

Imposta password temporanee per root e `sid`. Vanno cambiate subito dopo il primo boot.

```sh
printf 'root:install\nsid:install\n' | arch-chroot /mnt chpasswd
```

Abilita sudo per gli utenti nel gruppo `sudo` e imposta permessi sicuri sul file sudoers.

```sh
mkdir -p /mnt/etc/sudoers.d
cat > /mnt/etc/sudoers.d/10-sudo-group <<'EOF'
%sudo ALL=(ALL:ALL) ALL
EOF
chmod 0440 /mnt/etc/sudoers.d/10-sudo-group
```

## 8. Initramfs per LUKS, LVM e ibernazione

Configura `mkinitcpio` per includere tastiera/layout italiano, sblocco LUKS, LVM e resume da swap cifrata.

```sh
sed -i 's/^HOOKS=.*/HOOKS=(base udev autodetect microcode modconf kms keyboard keymap block encrypt lvm2 resume filesystems fsck)/' /mnt/etc/mkinitcpio.conf
```

Rigenera gli initramfs per `linux` e `linux-lts` con gli hook appena configurati.

```sh
arch-chroot /mnt mkinitcpio -P
```

## 9. systemd-boot

Installa `systemd-boot` nella ESP montata su `/boot`.

```sh
arch-chroot /mnt bootctl install
```

Crea la directory per le voci Boot Loader Specification.

```sh
mkdir -p /mnt/boot/loader/entries
```

Imposta Arch con kernel `linux` come default e lascia 5 secondi per scegliere il kernel LTS.

```sh
cat > /mnt/boot/loader/loader.conf <<'EOF'
default arch.conf
timeout 5
console-mode max
editor yes
EOF
```

Crea la voce default con kernel `linux`. `cryptdevice` apre LUKS con discard, `rootflags=subvol=@` monta il subvolume root e `resume` abilita ibernazione.

```sh
cat > /mnt/boot/loader/entries/arch.conf <<EOF
title Arch Linux
linux /vmlinuz-linux
initrd /amd-ucode.img
initrd /initramfs-linux.img
options cryptdevice=UUID=${CRYPT_UUID}:cryptroot:allow-discards root=/dev/mapper/vg0-root rootflags=subvol=@ resume=UUID=${SWAP_UUID} rw
EOF
```

Crea la voce di emergenza con kernel `linux-lts`, stesso layout LUKS/LVM/Btrfs e stesso resume.

```sh
cat > /mnt/boot/loader/entries/arch-lts.conf <<EOF
title Arch Linux LTS
linux /vmlinuz-linux-lts
initrd /amd-ucode.img
initrd /initramfs-linux-lts.img
options cryptdevice=UUID=${CRYPT_UUID}:cryptroot:allow-discards root=/dev/mapper/vg0-root rootflags=subvol=@ resume=UUID=${SWAP_UUID} rw
EOF
```

Crea la voce UEFI NVRAM `Arch Linux` puntata a systemd-boot sulla ESP. Al termine verifica che sia presente nel BootOrder e, se necessario, impostala come prima voce di avvio.

```sh
efibootmgr --create --disk /dev/nvme0n1 --part 1 --loader '\EFI\systemd\systemd-bootx64.efi' --label 'Arch Linux'
```

## 10. Servizi

Abilita la rete al boot.

```sh
arch-chroot /mnt systemctl enable NetworkManager.service
```

Abilita SSH al boot, utile per recupero e amministrazione remota.

```sh
arch-chroot /mnt systemctl enable sshd.service
```

Abilita TRIM periodico. È coerente con la scelta di consentire discard attraverso LUKS.

```sh
arch-chroot /mnt systemctl enable fstrim.timer
```

## 11. Verifiche

Controlla ESP, LUKS, LVM, Btrfs e UUID.

```sh
lsblk -f /dev/nvme0n1
```

Verifica che tutti i subvolumi siano montati nei punti corretti con le opzioni Btrfs previste.

```sh
findmnt -R /mnt
```

Conferma che la swap cifrata da 160GiB sia attiva e recupera l'UUID usato da `resume=`.

```sh
swapon --show --output NAME,TYPE,SIZE,USED,PRIO,UUID
```

Verifica che systemd-boot trovi loader config e voce default.

```sh
arch-chroot /mnt bootctl status
```

Verifica che la voce UEFI `Arch Linux` esista e punti a `\EFI\systemd\systemd-bootx64.efi`.

```sh
efibootmgr -v
```

Conferma che rete, SSH e TRIM periodico siano abilitati.

```sh
arch-chroot /mnt systemctl is-enabled NetworkManager.service sshd.service fstrim.timer
```

Scarica i buffer su disco prima del reboot.

```sh
sync
```

## 12. Primo boot

Riavvia nel sistema installato. Rimuovi la chiavetta se necessario o scegli `Arch Linux` dal boot menu.

```sh
reboot
```

Al prompt LUKS usa la passphrase temporanea `install` con layout italiano.

Dopo il primo boot cambiare subito le credenziali:

Cambia password utente, password root e passphrase LUKS temporanea.

```sh
passwd
sudo passwd root
sudo cryptsetup luksChangeKey /dev/nvme0n1p2
```

## 13. Hardening post-install

Il valore predefinito tipico di `umask` è `0022`: i nuovi file vengono creati come `0644` e le nuove directory come `0755`. Questo lascia permessi di lettura/accesso a `others`, troppo permissivi per un laptop personale.

Il gruppo primario dell'utente `sid` è `sid` e non contiene altri utenti; quindi è accettabile mantenere permessi di lettura/accesso per il gruppo privato, rimuovendo invece ogni permesso a `others`.

Configura `umask` a `027` per le nuove sessioni login e applicala anche alla shell corrente, così i comandi successivi della procedura creano file con permessi più restrittivi.

```sh
sudo cp /etc/login.defs /etc/login.defs.bak
sudo sed -i 's/^UMASK[[:space:]].*/UMASK\t\t027/' /etc/login.defs
umask 027
```

`pam_umask.so` è già attivo in `/etc/pam.d/system-login`; quando SDDM verrà installato userà lo stesso stack PAM, quindi il valore di `/etc/login.defs` verrà applicato alle nuove sessioni login/KDE senza dover impostare `umask` in `.bashrc`. Per applicarlo a tutti i processi grafici futuri, fai logout/login o reboot prima di iniziare a usare stabilmente KDE e gli applicativi.

Effetto atteso dopo logout/login o reboot:

```text
nuovi file:      0640
nuove directory: 0750
others:          nessun permesso
```

Adegua anche i permessi già presenti in `/home/sid`:

```sh
find /home/sid -xdev \( -type f -o -type d \) \( -perm /020 -o -perm /007 \) -exec chmod g-w,o-rwx {} +
```

Questo riallinea file e directory esistenti alla policy scelta senza seguire symlink e senza toccare socket, FIFO o device. Rimuove la scrittura al gruppo e tutti i permessi a `others`, preservando gli eventuali bit di esecuzione già presenti per owner/gruppo.

Esempi di trasformazione:

```text
0644 -> 0640
0755 -> 0750
0660 -> 0640
0770 -> 0750
0600 -> 0600
0700 -> 0700
```

Verifica dell'esistente:

```sh
find /home/sid -xdev \( -type f -o -type d \) -perm /007 -printf '%M %u:%g %p\n'
find /home/sid -xdev \( -type f -o -type d \) -perm /020 -printf '%M %u:%g %p\n'
```

Entrambi i comandi non dovrebbero stampare nulla. Eventuali processi ancora avviati dalla vecchia sessione possono però creare nuovi file con `0022` fino al prossimo logout/login o reboot.

## 14. KDE Plasma

Aggiorna il sistema e installa KDE Plasma dai repository Arch correnti. `plasma-meta` installa l'ambiente Plasma, inclusi `plasma-pa` e l'applet audio corretta per PipeWire/PulseAudio; `sddm` fornisce il display manager grafico. Le applicazioni KDE utili vengono installate esplicitamente invece di usare `kde-applications-meta`, per evitare il set completo di applicazioni e in particolare la catena `kde-applications-meta` -> `kde-multimedia-meta` -> `kmix`. Su questo portatile `kmix` aggiungeva una seconda icona audio grigia con `No mixer device available`, ridondante rispetto all'applet audio di Plasma.

```sh
sudo pacman -Syu --needed --noconfirm plasma-meta sddm dolphin konsole kate spectacle ark okular gwenview elisa kdeconnect
```

Installa e abilita Bluetooth. Sul PX13 con kernel 7.0.12 il controller MediaTek viene inizializzato correttamente dal kernel; serve solo avere `bluetooth.service` attivo per usarlo da KDE/Bluedevil. `bluez-utils` aggiunge strumenti di diagnostica come `bluetoothctl`.

```sh
sudo pacman -S --needed --noconfirm bluez bluez-utils
sudo systemctl enable --now bluetooth.service
```

Abilita SDDM al boot, così il sistema avvia automaticamente il login grafico KDE.

```sh
sudo systemctl enable sddm.service
```

Conferma che SDDM sia abilitato.

```sh
systemctl is-enabled sddm.service
```

Verifica che i profili energetici siano disponibili. L'output atteso include `power-saver`, `balanced` e `performance`, con driver `amd_pstate` e `platform_profile`.

```sh
powerprofilesctl
```

`asusctl` non è necessario per questa configurazione: le funzioni principali utili su questo modello sono esposte dal kernel tramite interfacce standard. Valutalo solo se servono funzioni ASUS non coperte, per esempio controlli avanzati Armoury/PPT o gestione ventole non accessibile via KDE/kernel.

Configura l'agent SSH utente per le chiavi private cifrate. Arch fornisce già le unità utente `ssh-agent.service` e `ssh-agent.socket` con il pacchetto `openssh`; serve abilitare il socket e pubblicare le variabili d'ambiente nelle nuove sessioni. `ksshaskpass` fornisce il prompt KDE e può salvare le passphrase in KWallet.

```sh
sudo pacman -S --needed --noconfirm ksshaskpass
mkdir -p ~/.config/environment.d
cat > ~/.config/environment.d/ssh-agent.conf <<'EOF'
SSH_AUTH_SOCK=${XDG_RUNTIME_DIR}/ssh-agent.socket
SSH_ASKPASS=/usr/bin/ksshaskpass
SSH_ASKPASS_REQUIRE=prefer
EOF
systemctl --user enable --now ssh-agent.socket
systemctl --user set-environment SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/ssh-agent.socket" SSH_ASKPASS=/usr/bin/ksshaskpass SSH_ASKPASS_REQUIRE=prefer
env SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/ssh-agent.socket" SSH_ASKPASS=/usr/bin/ksshaskpass SSH_ASKPASS_REQUIRE=prefer dbus-update-activation-environment --systemd SSH_AUTH_SOCK SSH_ASKPASS SSH_ASKPASS_REQUIRE
```

Aggiungi un default OpenSSH per caricare nell'agent le chiavi al primo uso. La direttiva va in fondo a `~/.ssh/config`, dopo gli host specifici, perché OpenSSH usa il primo valore applicabile.

```sshconfig
Host *
    AddKeysToAgent yes
```

Dopo il login in KDE, al primo uso di una chiave privata cifrata, OpenSSH chiederà la passphrase tramite `ksshaskpass` e la caricherà nell'agent.

Riavvia per passare dal login testuale alla sessione grafica. Al riavvio SDDM deve mostrare il login KDE.

```sh
reboot
```

Installa i dizionari Hunspell usati dal controllo ortografico di KDE Plasma per italiano e inglese.

```sh
sudo pacman -S --needed --noconfirm hunspell-it hunspell-en_us
```

I dizionari Hunspell non modificano il locale di sistema: `/etc/locale.conf` resta con applicativi in inglese (`LANG=en_US.UTF-8`) e convenzioni numeriche/valuta italiane (`LC_*` italiani). Configurano solo le lingue disponibili per lo spell check. Nota tecnica: Plasma usa Sonnet, un componente di KDE Frameworks, come backend per il controllo ortografico.

Configura lo spell check globale di KDE Plasma dall'interfaccia grafica:

```sh
systemsettings kcmspellchecking
```

Nel pannello `Spell Check` imposta:

- `Selected default language` / `Default language`: italiano (`it_IT`).
- `Detect language automatically` / `Enable autodetection of language`: attivo, per testi misti italiano/inglese.
- `Additional Spell Checking Languages` / `Preferred languages`: aggiungi inglese statunitense (`en_US`).
- `Enable automatic spell checking`: attivo se vuoi la sottolineatura automatica nelle applicazioni KDE compatibili.

Installa e abilita il demone standard per i profili energetici. Su questo PX13 il kernel espone già `/sys/firmware/acpi/platform_profile` con `quiet`, `balanced` e `performance`; `power-profiles-daemon` rende questi profili disponibili a KDE/PowerDevil senza richiedere tool ASUS specifici.

```sh
sudo pacman -S --needed --noconfirm power-profiles-daemon
sudo systemctl enable --now power-profiles-daemon.service
```

Se KDE mostra ancora `Power Profile: Not available` dopo l'installazione del demone, riavvia PowerDevil nella sessione utente o fai logout/login:

```sh
systemctl --user restart plasma-powerdevil.service
```

Dopo il riavvio di PowerDevil l'applet KDE dovrebbe mostrare i profili energetici, con `Balanced` come profilo tipico iniziale.

Configura il limite di carica persistente della batteria. KDE espone la voce da `System Settings` -> `Power Management` -> `Advanced Power Settings` -> `Charge Limit` -> `Stop charging at`, e su questo PX13 il kernel espone l'attributo standard `/sys/class/power_supply/BAT0/charge_control_end_threshold`. Con `powerdevil 6.6.5` il valore impostato dalla GUI viene applicato correttamente a runtime, ma non viene salvato da PowerDevil e non viene riapplicato al boot: dopo un riavvio il firmware/kernel riparte da `100`.

Questo comportamento è un problema noto upstream di KDE/PowerDevil, tracciato da KDE Bug `450551` (`Battery charge limit is not preserved after reboot on many laptops that support charge limits; need to write it on every boot`) e dal duplicato `452533` (`Stop charging at not saved after restart`). Le discussioni upstream citano anche merge request correlate `powerdevil!253`, `powerdevil!290` e `powerdevil!621`, ma al momento della configurazione locale il fix non è ancora disponibile nei pacchetti Arch installati. Finché PowerDevil non gestirà nativamente la persistenza, usa una regola udev come trigger hotplug, un servizio systemd oneshot con retry e un timer systemd `OnBootSec=30s` per riapplicare al boot lo stesso valore desiderato, `85`.

Nota operativa: se in futuro cambi intenzionalmente il valore permanente dalla GUI KDE, aggiorna anche il servizio systemd con lo stesso valore. In caso contrario la GUI può cambiare la soglia solo per la sessione corrente, mentre al prossimo boot la configurazione locale riporterà `BAT0` a `85`.

Creazione della regola udev, del servizio systemd e del timer:

```sh
cat > /tmp/99-px13-battery-charge-limit.rules <<'EOF_UDEV'
# ASUS ProArt PX13 HN7306EAC battery charge-limit workaround.
# KDE PowerDevil bug 450551: many laptops reset charge_control_end_threshold to 100 on reboot.
# Start the retrying systemd service whenever BAT0 is reported.
ACTION=="add|change", SUBSYSTEM=="power_supply", KERNEL=="BAT0", ATTR{type}=="Battery", TAG+="systemd", ENV{SYSTEMD_WANTS}+="px13-battery-charge-limit.service"
EOF_UDEV

cat > /tmp/px13-battery-charge-limit.service <<'EOF_SYSTEMD'
[Unit]
Description=ASUS PX13 battery charge-limit workaround
Documentation=https://bugs.kde.org/show_bug.cgi?id=450551

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do if [ -w /sys/class/power_supply/BAT0/charge_control_end_threshold ]; then printf "85\n" > /sys/class/power_supply/BAT0/charge_control_end_threshold; exit 0; fi; sleep 1; done; exit 1'
TimeoutStartSec=20
EOF_SYSTEMD

cat > /tmp/px13-battery-charge-limit.timer <<'EOF_TIMER'
[Unit]
Description=Apply ASUS PX13 battery charge limit after boot
Documentation=https://bugs.kde.org/show_bug.cgi?id=450551

[Timer]
OnBootSec=30s
AccuracySec=1s
Unit=px13-battery-charge-limit.service

[Install]
WantedBy=timers.target
EOF_TIMER

sudo install -m 0644 /tmp/99-px13-battery-charge-limit.rules /etc/udev/rules.d/99-px13-battery-charge-limit.rules
sudo install -m 0644 /tmp/px13-battery-charge-limit.service /etc/systemd/system/px13-battery-charge-limit.service
sudo install -m 0644 /tmp/px13-battery-charge-limit.timer /etc/systemd/system/px13-battery-charge-limit.timer
sudo udevadm control --reload
sudo systemctl daemon-reload
sudo systemctl enable --now px13-battery-charge-limit.timer
sudo systemctl start px13-battery-charge-limit.service
sudo udevadm trigger --action=change /sys/class/power_supply/BAT0
sudo udevadm settle
```

Verifica:

```sh
systemctl is-enabled px13-battery-charge-limit.timer
systemctl show -p Result px13-battery-charge-limit.service
cat /sys/class/power_supply/BAT0/charge_control_end_threshold
```

L'output atteso è `enabled`, `Result=success` e `85`. KDE dovrebbe mostrare `Stop charging at: 85%` perché il timer locale riapplica il limite dopo il completamento dell'avvio.
## 15. Audio interno TAS2783

Sul PX13 HN7306EAC con kernel 7.0.12 il driver SoundWire/TAS2783 è presente, ma `linux-firmware` non contiene ancora i blob di calibrazione ASUS. 
Il kernel cerca `1714-1-8.bin` e `1714-1-B.bin`, fallisce il caricamento, e PipeWire mostra solo `Dummy Output`.

Nota: in futuro si può rimuovere questa procedura se gli stessi firmware entrano in `linux-firmware`.

I nomi lato Linux sono derivati dal driver e dal device: subsystem ASUS `0x1714`, SoundWire link `1`, indirizzi slave `0x8` e `0xB`. Nel driver Windows ASUS gli stessi blob erano nominati `1714-1-0x8.bin` e `1714-1-0xB.bin`; sono stati installati rinominandoli nei nomi che il kernel Linux richiede. Se in futuro `dmesg` mostrasse nomi diversi, vanno seguiti i nomi richiesti dal kernel in uso.

Fonte firmware: driver ufficiale ASUS SmartAmp per `HN7306EAC`:

```text
https://dlcdnets.asus.com/pub/ASUS/nb/Image/Driver/Audio/47519/SmartAMP_TI_DCH_TexasInstruments_Z_V6.3.1.15_47519.exe?model=HN7306EAC
```

Riferimento procedura: https://gist.github.com/cryptob1/f62aaf8517df2e540f447347f42c7a03.

Nota su `iommu=pt`: il gist `cryptob1` lo cita come parametro consigliato per Strix Halo e l'issue CachyOS `https://github.com/CachyOS/linux-cachyos/issues/737` lo riporta come workaround per alcuni problemi di boot/fault AMD-Vi. Su questa installazione non è parte del fix audio: il test con `iommu=pt` non ha risolto il problema suspend/resume TAS2783, quindi la riga kernel non è stata utilizzata.

Strumenti usati:

```sh
sudo pacman -S --needed --noconfirm 7zip wine wine-mono inotify-tools rsync curl alsa-utils
```

L'installer ASUS è un wrapper Inno/7z che estrae il payload vero solo per pochi istanti in `%TEMP%`. Per catturare i file, esegui l'installer con Wine e copia ripetutamente le directory temporanee mentre il setup è in esecuzione:

```sh
WORK=/tmp/px13-tas2783
URL='https://dlcdnets.asus.com/pub/ASUS/nb/Image/Driver/Audio/47519/SmartAMP_TI_DCH_TexasInstruments_Z_V6.3.1.15_47519.exe?model=HN7306EAC'
mkdir -p "$WORK"
cd "$WORK"
curl -fL -A 'Mozilla/5.0' -o smartamp.exe "$URL"

export WINEPREFIX="$WORK/wineprefix" WINEDEBUG=-all
wineboot -i >/dev/null 2>&1 || true

rm -rf snapshot-fast
mkdir -p snapshot-fast
TEMP="$WINEPREFIX/drive_c/users/$USER/AppData/Local/Temp"

(
  end=$((SECONDS+90))
  while [ "$SECONDS" -lt "$end" ]; do
    for d in "$TEMP"/is-* "$TEMP"/Setup_*; do
      [ -d "$d" ] && rsync -a "$d"/ snapshot-fast/ 2>/dev/null || true
    done
    sleep 0.05
  done
) &
WATCHER=$!

wine "$WORK/smartamp.exe" /SP- /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=Z:\\tmp\\px13-tas2783\\install.log || true
sleep 10
kill "$WATCHER" 2>/dev/null || true
wait "$WATCHER" 2>/dev/null || true
```

I file firmware dovrebbero trovarsi in una directory simile a questa:

```text
/tmp/px13-tas2783/snapshot-fast/Soundwire_SmartAMP_TI_DCH_TexasInstruments_Z_V6.3.1.15_47519/20260617184605/Firmwares/
```

Installazione firmware:

```sh
SRC_DIR=$(dirname "$(find /tmp/px13-tas2783/snapshot-fast -type f -name '1714-1-0x8.bin' | head -n 1)")
sudo install -m 644 "$SRC_DIR/1714-1-0x8.bin" /lib/firmware/1714-1-8.bin
sudo install -m 644 "$SRC_DIR/1714-1-0xB.bin" /lib/firmware/1714-1-B.bin
sudo install -d -m 755 /lib/firmware/ti/audio/tas2783
sudo install -m 644 "$SRC_DIR/1714-1-0x8.bin" /lib/firmware/ti/audio/tas2783/1714-1-8.bin
sudo install -m 644 "$SRC_DIR/1714-1-0xB.bin" /lib/firmware/ti/audio/tas2783/1714-1-B.bin
```

Configurazione WirePlumber. Il profilo `pro-audio` espone il PCM degli speaker TAS2783 come `pro-output-2`. Sullo stesso profilo il kernel espone anche il capture SmartAmp `pro-input-3` (`SDW1-PIN4-CAPTURE-SmartAmp`), che non è un microfono utente e può fallire con errori SoundWire `-22` quando Plasma enumera le sorgenti audio. Per questo la configurazione disabilita solo quel nodo e preferisce il DMIC interno `pro-input-4` come sorgente di input.

```sh
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
cat > ~/.config/wireplumber/wireplumber.conf.d/51-strix-halo-audio.conf <<'EOF'
monitor.alsa.rules = [
  {
    matches = [
      { device.name = "alsa_card.pci-0000_c4_00.5-platform-amd_sdw" }
    ]
    actions = {
      update-props = {
        device.profile = "pro-audio"
      }
    }
  }
  {
    matches = [
      { node.name = "alsa_output.pci-0000_c4_00.5-platform-amd_sdw.pro-output-2" }
    ]
    actions = {
      update-props = {
        session.suspend-timeout-seconds = 0
        node.description = "Internal Speakers (TAS2783)"
      }
    }
  }
  {
    matches = [
      { node.name = "alsa_input.pci-0000_c4_00.5-platform-amd_sdw.pro-input-3" }
    ]
    actions = {
      update-props = {
        node.disabled = true
      }
    }
  }
  {
    matches = [
      { node.name = "alsa_input.pci-0000_c4_00.5-platform-amd_sdw.pro-input-4" }
    ]
    actions = {
      update-props = {
        node.description = "Internal Microphones (DMIC)"
        priority.session = 2600
      }
    }
  }
]
EOF
```

Riavvia per far riprovare il caricamento firmware durante il probe del driver:

```sh
sudo reboot
```

Verifica post-reboot:

```sh
sudo journalctl -k -b --no-pager | rg -i 'tas2783|1714-1|playback without fw|SDW1-PIN4-CAPTURE-SmartAmp|Program transport'
wpctl status
pactl list sources short
pactl set-default-sink alsa_output.pci-0000_c4_00.5-platform-amd_sdw.pro-output-2
pactl set-default-source alsa_input.pci-0000_c4_00.5-platform-amd_sdw.pro-input-4
speaker-test -D pipewire -c 2 -r 48000 -F S16_LE -t sine -f 440 -l 1
```

Dopo il reboot il journal kernel non deve mostrare errori firmware TAS2783, `playback without fw`, né nuovi errori `Program transport params failed` sul nodo `SDW1-PIN4-CAPTURE-SmartAmp`. PipeWire deve esporre `Internal Speakers (TAS2783)` come sink, `Internal Microphones (DMIC)` come source, e non deve esporre `alsa_input.pci-0000_c4_00.5-platform-amd_sdw.pro-input-3`. Il test stereo PipeWire deve produrre un tono udibile. Evita come test principale `/usr/share/sounds/alsa/Front_Center.wav`: è mono, mentre il PCM TAS2783 espone solo stereo a 48 kHz e può produrre risultati fuorvianti.

Workaround suspend/resume.

Il solo firmware più WirePlumber rende gli speaker funzionanti dopo boot pulito, ma non basta dopo suspend/resume. Con `s2idle` gli speaker TAS2783 possono restare muti o il playback può fallire sotto SoundWire. Il workaround combina due parti:

- regola udev per impedire D3cold sul bridge PCI `0000:00:08.1` e sul controller ACP `0000:c4:00.5`;
- servizio systemd post-resume che resetta il controller ACP `0000:c4:00.5`, forza la catena audio/SoundWire attiva e riapplica i controlli mixer TAS2783.

Riferimento principale per il reset ACP post-resume: `https://github.com/brainchillz/asus-proart-px13-linux-speaker-fix`. La soluzione locale mantiene lo stesso principio, cioè reset del parent PCI ACP dopo thaw invece di un hook `systemd-sleep`, e aggiunge prevenzione D3cold e riapplicazione dei controlli mixer TAS2783.

Creazione della regola udev:

```sh
cat > /tmp/99-px13-audio-d3cold.rules <<'EOF_UDEV'
# ASUS ProArt PX13 HN7306EAC TAS2783 suspend workaround.
# Prevent ACP bridge/controller D3cold; otherwise SoundWire TAS2783 resume can time out.
SUBSYSTEM=="pci", KERNEL=="0000:00:08.1", ATTR{d3cold_allowed}="0", ATTR{power/control}="on"
SUBSYSTEM=="pci", KERNEL=="0000:c4:00.5", ATTR{d3cold_allowed}="0", ATTR{power/control}="on"
EOF_UDEV

sudo install -m 0644 /tmp/99-px13-audio-d3cold.rules /etc/udev/rules.d/99-px13-audio-d3cold.rules
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=pci --action=change /sys/bus/pci/devices/0000:00:08.1 /sys/bus/pci/devices/0000:c4:00.5
```

Creazione dello script post-resume:

```sh
cat > /tmp/px13-audio-resume <<'EOF_SCRIPT'
#!/usr/bin/env bash
set -uo pipefail

PCI_BRIDGE=0000:00:08.1
PCI_ACP=0000:c4:00.5
PCI_ACP_DRIVER=/sys/bus/pci/drivers/snd_pci_ps

log() {
  printf 'px13-audio-resume: %s\n' "$*"
}

force_pci_on() {
  local dev_path

  dev_path="/sys/bus/pci/devices/$1"
  [ -e "$dev_path" ] || {
    log "PCI device $1 is not present"
    return 0
  }

  [ -w "$dev_path/d3cold_allowed" ] && printf '0\n' > "$dev_path/d3cold_allowed"
  [ -w "$dev_path/power/control" ] && printf 'on\n' > "$dev_path/power/control"
}

force_audio_runtime_on() {
  local dev_path

  for dev_path in \
    /sys/bus/soundwire/devices/sdw:0:1:0102:0000:01:8 \
    /sys/bus/soundwire/devices/sdw:0:1:0102:0000:01:b \
    /sys/bus/soundwire/devices/sdw:0:1:025d:0721:01 \
    /sys/bus/platform/devices/amd_sdw \
    /sys/bus/platform/devices/amd_sdw_manager.0 \
    /sys/bus/platform/devices/amd_sdw_manager.1 \
    /sys/bus/platform/devices/amd_ps_sdw_dma.0
  do
    [ -w "$dev_path/power/control" ] && printf 'on\n' > "$dev_path/power/control"
  done
}

reset_acp() {
  [ -e "/sys/bus/pci/devices/$PCI_ACP" ] || {
    log "ACP device $PCI_ACP is not present"
    return 1
  }
  [ -w "$PCI_ACP_DRIVER/unbind" ] && [ -w "$PCI_ACP_DRIVER/bind" ] || {
    log "ACP driver bind controls are not writable"
    return 1
  }

  timeout 30 sh -c 'printf "%s" "$1" > "$2/unbind"' sh "$PCI_ACP" "$PCI_ACP_DRIVER" || {
    log "unbind failed for $PCI_ACP"
    return 1
  }

  sleep 2
  force_pci_on "$PCI_BRIDGE"

  timeout 30 sh -c 'printf "%s" "$1" > "$2/bind"' sh "$PCI_ACP" "$PCI_ACP_DRIVER" || {
    log "bind failed for $PCI_ACP"
    return 1
  }

  sleep 3
}

restore_mixer() {
  amixer -q -c amdsoundwire sset 'tas2783-1 Amp' 20 || true
  amixer -q -c amdsoundwire sset 'tas2783-2 Amp' 20 || true
  amixer -q -c amdsoundwire sset 'tas2783-1 Speaker' 200 || true
  amixer -q -c amdsoundwire sset 'tas2783-2 Speaker' 200 || true
  amixer -q -c amdsoundwire sset 'Left Spk' on || true
  amixer -q -c amdsoundwire sset 'Right Spk' on || true
  amixer -q -c amdsoundwire sset 'Left Spk2' on || true
  amixer -q -c amdsoundwire sset 'Right Spk2' on || true
}

force_pci_on "$PCI_BRIDGE"
force_pci_on "$PCI_ACP"
force_audio_runtime_on
reset_acp
force_pci_on "$PCI_BRIDGE"
force_pci_on "$PCI_ACP"
force_audio_runtime_on
restore_mixer
log done
EOF_SCRIPT

bash -n /tmp/px13-audio-resume
sudo install -m 0755 /tmp/px13-audio-resume /usr/local/sbin/px13-audio-resume
```

Creazione e abilitazione del servizio systemd:

```sh
cat > /tmp/px13-audio-resume.service <<'EOF_SERVICE'
[Unit]
Description=ASUS PX13 TAS2783 audio resume workaround
After=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/px13-audio-resume
TimeoutStartSec=60

[Install]
WantedBy=suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
EOF_SERVICE

sudo install -m 0644 /tmp/px13-audio-resume.service /etc/systemd/system/px13-audio-resume.service
sudo systemctl daemon-reload
sudo systemctl enable px13-audio-resume.service
```

Verifica dello stato installato:

```sh
systemctl is-enabled px13-audio-resume.service
test -x /usr/local/sbin/px13-audio-resume
test -f /etc/udev/rules.d/99-px13-audio-d3cold.rules
for d in /sys/bus/pci/devices/0000:00:08.1 /sys/bus/pci/devices/0000:c4:00.5; do
  printf '%s ' "$d"
  printf 'd3cold_allowed=' && cat "$d/d3cold_allowed"
  printf 'control=' && cat "$d/power/control"
done
```

Test suspend/resume del workaround:

```sh
sudo rtcwake -m no -s 25
sudo systemctl suspend
journalctl -b -u px13-audio-resume.service --no-pager
wpctl status
speaker-test -D pipewire -c 2 -r 48000 -F S16_LE -t sine -f 660 -l 2
```

Per disabilitare il suspend/resume workaround:

```sh
sudo systemctl disable px13-audio-resume.service
sudo mv /etc/udev/rules.d/99-px13-audio-d3cold.rules /etc/udev/rules.d/99-px13-audio-d3cold.rules.disabled
sudo udevadm control --reload
```

Per riabilitarlo:

```sh
sudo mv /etc/udev/rules.d/99-px13-audio-d3cold.rules.disabled /etc/udev/rules.d/99-px13-audio-d3cold.rules
sudo udevadm control --reload
sudo systemctl enable px13-audio-resume.service
```

## 16. Applicativi base

Installa gli applicativi utente base.

```sh
sudo pacman -S --needed --noconfirm aria2 firefox keepassxc uv nvm obsidian
```

Inizializza `nvm` per le nuove shell Bash dell'utente. Il pacchetto Arch installa gli script in `/usr/share/nvm`, ma richiede il `source` nel profilo shell dell'utente.

```sh
printf '\n# Enable nvm from Arch package\nsource /usr/share/nvm/init-nvm.sh\n' >> ~/.bashrc
```

Verifica che i pacchetti applicativi siano installati e che `uv` e `nvm` siano disponibili. Le versioni esatte dipendono dallo stato dei repository Arch al momento dell'installazione.

```sh
pacman -Q firefox keepassxc uv nvm obsidian
uv --version
bash -lc 'source /usr/share/nvm/init-nvm.sh && nvm --version'
```

Per Firefox, dopo l'installazione dei dizionari Hunspell riavvia il browser se era già aperto; nei campi di testo usa il menu contestuale `Languages` per selezionare italiano o inglese quando necessario.

Obsidian è un'app Electron e non usa necessariamente lo spell check globale di KDE Plasma. Configura la lingua da `Settings` -> `Editor` -> `Spellcheck languages`: usa italiano come lingua principale e aggiungi inglese statunitense se vuoi poterlo selezionare quando scrivi testo in inglese. Le preferenze e i dizionari scaricati da Obsidian sono globali dell'app, sotto `~/.config/obsidian`, mentre le impostazioni del vault restano sotto `.obsidian/`.

## 17. Note hardware PX13

Le discussioni storiche sul PX13 citano problemi con kernel 6.11/6.12, Bluetooth MediaTek, NVIDIA, retroilluminazione tastiera e audio. Sul modello `ProArt PX13 HN7306EAC` con Ryzen AI MAX+ 395 / Radeon 8060S e kernel `7.0.12`, la configurazione verificata è questa:

- Grafica: `amdgpu` caricato per `Strix Halo [Radeon Graphics / Radeon 8050S Graphics / Radeon 8060S Graphics]`.
- Wi-Fi: MT7925 gestito da `mt7925e`.
- Bluetooth: controller MediaTek gestito da `btusb`; funziona dopo aver abilitato `bluetooth.service`.
- Webcam: `ASUS FHD webcam` rilevata da PipeWire/KDE.
- Touch e penna: dispositivi `ELAN9008:00 04F3:4631` e `Stylus` rilevati.
- Tastiera ASUS: moduli `asus_nb_wmi`, `asus_wmi`, `asus_armoury` caricati; retroilluminazione disponibile come `/sys/class/leds/asus::kbd_backlight` con livelli `0..3`.
- Profili energetici: disponibili via `power-profiles-daemon` usando `amd_pstate` e `platform_profile`.
- Limite carica batteria: il kernel espone `/sys/class/power_supply/BAT0/charge_control_end_threshold`; il valore persistente locale è `85`, riapplicato al boot da `/etc/systemd/system/px13-battery-charge-limit.timer` e `/etc/systemd/system/px13-battery-charge-limit.service`, con trigger udev in `/etc/udev/rules.d/99-px13-battery-charge-limit.rules`, per aggirare il bug KDE/PowerDevil `450551`.
- Audio interno: speaker TAS2783 funzionanti dopo installazione dei blob ASUS SmartAmp estratti dal driver Windows ufficiale, configurazione WirePlumber `pro-audio` e workaround post-resume `px13-audio-resume.service`.

## 18. Problemi conosciuti

Il limite di carica configurato dalla GUI KDE/PowerDevil non è persistente su questo PX13 con i pacchetti attuali: dopo reboot il valore kernel può tornare a `100`. È un problema noto upstream, KDE Bug `450551`, con duplicato `452533`. La configurazione locale usa `px13-battery-charge-limit.timer`, `px13-battery-charge-limit.service` e una regola udev di trigger per riportare automaticamente `BAT0` a `85` al boot; questi file vanno rimossi o aggiornati quando PowerDevil includerà un fix nativo.

~~Al momento l'ibernazione dalla sessione Plasma Wayland non è affidabile: può bloccarsi durante l'ingresso in hibernate o riprendere con artefatti/lockup grafici, quindi va considerata non funzionante finché non viene corretto il problema nel kernel/driver grafico.~~ (fixed con il kernel 7.0.13)
