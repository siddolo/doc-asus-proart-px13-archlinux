# Ollama ROCm su ASUS ProArt PX13

Questa guida descrive l'installazione di Ollama su Arch Linux con backend ROCm per AMD Ryzen AI Max+ 395 / Radeon 8060S e directory modelli dedicata in `/srv/models/ollama`. Per il motivo di quel path, vedi lo schema di partizionamento in [Installazione base Arch Linux](installazione-base-arch-linux.md), dove `/srv/models` è montato dal subvolume Btrfs `@models` dedicato ai modelli LLM.

La configurazione usa il servizio systemd fornito dal pacchetto Arch e drop-in sotto `/etc/systemd/system/ollama.service.d/`. La configurazione kernel ottimizzata per workload AI è documentata in [Kernel AI tuning](kernel-ai-tuning.md). Il backend Vulkan è documentato separatamente in [Ollama Vulkan](ollama-vulkan.md).

## 1. Pacchetto e backend

`ollama-rocm` installa il backend ROCm di Ollama per GPU AMD. La variante Vulkan è installabile in parallelo e viene gestita come backend alternativo nella guida [Ollama Vulkan](ollama-vulkan.md).

Se `ollama-rocm` e `ollama-vulkan` sono installati insieme, la selezione del backend va resa esplicita con un solo drop-in systemd attivo alla volta. Systemd carica tutti i file `*.conf` presenti nella directory del servizio; per questo `backend-rocm.conf` e `backend-vulkan.conf` non devono essere attivi insieme. La convenzione usata qui è: il backend attivo ha estensione `.conf`, il backend inattivo resta presente con estensione `.conf.disabled`.

Installa Ollama ROCm dai repository Arch.

```sh
sudo pacman -Syu --needed --noconfirm ollama-rocm
```

Verifica i pacchetti principali installati.

```sh
pacman -Q ollama ollama-rocm rocm-core hipblas rocminfo
```

## 2. Directory modelli

La directory dei modelli viene spostata da `/var/lib/ollama` a `/srv/models/ollama`.

Il motivo è nella guida di installazione base: [Installazione base Arch Linux](installazione-base-arch-linux.md) crea un subvolume Btrfs dedicato `@models` e lo monta in `/srv/models`. Quel subvolume nasce per i modelli LLM, che possono occupare decine di GiB e hanno caratteristiche diverse da root e home. Tenerli sotto `/srv/models` evita di gonfiare il subvolume root, rende più chiaro cosa escludere o trattare diversamente in snapshot/backup e centralizza lo storage dei modelli anche per altri motori AI.

Verifica che `/srv/models` sia montato sul subvolume dedicato.

```sh
findmnt /srv/models
```

Output atteso:

```text
/srv/models /dev/mapper/vg0-root[/@models] btrfs ... subvol=/@models
```

Crea la directory per Ollama e assegnala all'utente di servizio.

```sh
sudo install -d -m 0750 -o ollama -g ollama /srv/models/ollama
```

## 3. Permessi GPU

Il servizio gira come utente `ollama`. Aggiungi questo utente al gruppo `render`, così può accedere ai device GPU ROCm anche se i permessi udev diventano più restrittivi.

```sh
sudo usermod -aG render ollama
```

Verifica l'appartenenza ai gruppi.

```sh
id ollama
```

L'output deve includere `render`.

## 4. Drop-in systemd

Il pacchetto Arch installa il servizio `/usr/lib/systemd/system/ollama.service`, con `OLLAMA_MODELS=/var/lib/ollama` di default. Non modificare il file del pacchetto: crea drop-in persistenti sotto `/etc/systemd/system/ollama.service.d/`.

```sh
sudo install -d -m 0755 /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_MODELS=/srv/models/ollama"
EOF
sudo chmod 0644 /etc/systemd/system/ollama.service.d/override.conf
```

Per attivare ROCm, disabilita prima l'eventuale drop-in Vulkan attivo. Il backend attivo deve essere uno solo.

```sh
if [ -f /etc/systemd/system/ollama.service.d/backend-vulkan.conf ]; then
  sudo mv /etc/systemd/system/ollama.service.d/backend-vulkan.conf \
    /etc/systemd/system/ollama.service.d/backend-vulkan.conf.disabled
fi
```

Riattiva il drop-in ROCm se esiste già come file disabilitato.

```sh
if [ -f /etc/systemd/system/ollama.service.d/backend-rocm.conf.disabled ]; then
  sudo mv /etc/systemd/system/ollama.service.d/backend-rocm.conf.disabled \
    /etc/systemd/system/ollama.service.d/backend-rocm.conf
fi
```

Se il drop-in ROCm non esiste ancora, crealo una sola volta. Il valore `rocm_v7_2` corrisponde alla directory backend installata in `/usr/lib/ollama/rocm_v7_2` su Ollama 0.30.10; dopo aggiornamenti maggiori controlla il nome effettivo della directory.

```sh
if [ ! -f /etc/systemd/system/ollama.service.d/backend-rocm.conf ]; then
  sudo tee /etc/systemd/system/ollama.service.d/backend-rocm.conf >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_LLM_LIBRARY=rocm_v7_2"
EOF
  sudo chmod 0644 /etc/systemd/system/ollama.service.d/backend-rocm.conf
fi
```

Ricarica systemd e abilita il servizio al boot.

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now ollama.service
```

## 5. Verifiche

Controlla che il servizio sia attivo e abilitato.

```sh
systemctl is-enabled ollama.service
systemctl is-active ollama.service
```

L'output atteso è:

```text
enabled
active
```

Verifica l'environment effettivo del servizio.

```sh
systemctl show -p Environment ollama.service
```

L'output deve includere:

```text
OLLAMA_MODELS=/srv/models/ollama
OLLAMA_LLM_LIBRARY=rocm_v7_2
```

Verifica che sia attivo un solo drop-in backend.

```sh
ls /etc/systemd/system/ollama.service.d/backend-*.conf
```

Con ROCm attivo deve comparire solo:

```text
/etc/systemd/system/ollama.service.d/backend-rocm.conf
```

Verifica permessi e ownership della directory modelli.

```sh
stat -c '%A %U:%G %n' /srv/models /srv/models/ollama /etc/systemd/system/ollama.service.d/override.conf
```

Output atteso per la directory Ollama:

```text
drwxr-x--- ollama:ollama /srv/models/ollama
```

Verifica la CLI e l'API locale.

```sh
ollama --version
ollama list
curl -fsS http://127.0.0.1:11434/api/tags
```

Subito dopo l'installazione `ollama list` può essere vuoto, perché non sono ancora stati scaricati modelli.

Verifica che ROCm veda la GPU integrata Strix Halo.

```sh
/opt/rocm/bin/rocm_agent_enumerator
/opt/rocm/bin/rocminfo | grep -Ei 'gfx1151|Marketing Name|AMD Radeon 8060S'
```

`rocm_agent_enumerator` deve includere `gfx1151`; `rocminfo` deve mostrare la Radeon 8060S.

## 6. Uso base

Scarica un modello piccolo per testare download, storage e inferenza.

```sh
ollama pull qwen3:0.6b
ollama run qwen3:0.6b
```

Durante o subito dopo l'esecuzione, controlla se il modello è caricato su GPU.

```sh
ollama ps
```

La colonna `PROCESSOR` indica se il modello è caricato in GPU, CPU o in modo misto.

## 7. Misura performance

Per misurare le performance in token/s usa `ollama run --verbose`: alla fine della risposta Ollama stampa direttamente tempi, conteggi token e velocità.

Esempio con il modello di test già scaricato nella sezione precedente:

```sh
ollama run --think=false --verbose qwen3:0.6b \
  "Scrivi una spiegazione breve di cosa fa systemd-boot su Arch Linux."
```

Esempio con `qwen3.6:27b`:

```text
ollama run --think=false --verbose qwen3.6:27b "Scrivi una spiegazione breve di cosa fa systemd-boot su Arch Linux."
**systemd-boot** (precedentemente noto come Gummiboot) è un bootloader semplice e rapido per sistemi UEFI, predefinito nelle installazioni standard di Arch Linux.

Ecco i suoi punti chiave:

- **Leggero e veloce**: Non include funzionalità complesse come menu grafici personalizzati o crittografia dei dischi al boot; il suo unico scopo è caricare il kernel e l'ambiente iniziale (initramfs).
- **Basato su UEFI**: Sfrutta le variabili UEFI del firmware per gestire la configurazione, senza bisogno di una partizione dedicata oltre a quella EFI (FAT32) già esistente.
- **Configurazione semplice**: I parametri di avvio sono definiti in file di testo semplici nella directory `/boot/loader/entries/`, rendendo facile l’aggiunta o la modifica delle voci di boot.
- **Integrazione con systemd**: Sebbene sia un componente indipendente, il nome riflette la sua origine nello stesso gruppo di sviluppatori; funziona bene nell’ecosistema Arch Linux grazie alla 
filosofia KISS (*Keep It Simple, Stupid*).

In sintesi: è una scelta minimalista, affidabile e trasparente per avviare Arch Linux su hardware UEFI moderno.

total duration:       18.035596669s  
load duration:        200.2276ms  
prompt eval count:    27 token(s)  
prompt eval duration: 89.411ms  
prompt eval rate:     301.98 tokens/s  
eval count:           218 token(s)  
eval duration:        17.08266s  
eval rate:            12.76 tokens/s

```

`prompt eval rate` misura il prompt processing, cioè la velocità con cui il modello elabora il prompt iniziale. `eval rate` misura la token generation, cioè la velocità di generazione della risposta. `load duration` è il tempo di caricamento del modello e non va confuso con la velocità di inferenza.

Per confronti sensati esegui una prima run di warm-up, poi confronta le run successive usando sempre stesso modello, stesso prompt e impostazioni equivalenti. Controlla con `ollama ps` che il modello sia caricato nello stesso modo, per esempio `100% GPU`.

Questa misura è utile per confrontare modifiche locali, come aggiornamenti pacchetto, tuning kernel o cambio backend. Non è un benchmark assoluto: modello, quantizzazione, lunghezza prompt, temperatura, contesto e stato termico del portatile influenzano il risultato.

## 8. Log e diagnostica

Leggi i log del servizio.

```sh
sudo journalctl -u ollama.service -b --no-pager
```

Mostra la configurazione completa del servizio, inclusi override.

```sh
systemctl cat ollama.service
```

Se Ollama non usa la GPU dopo un aggiornamento o dopo modifiche al boot, verifica nell'ordine:

- `ollama-rocm` installato;
- `/etc/systemd/system/ollama.service.d/backend-rocm.conf` è l'unico drop-in backend attivo;
- `/opt/rocm/bin/rocm_agent_enumerator` contiene `gfx1151`;
- `ollama` appartiene al gruppo `render`;
- il servizio è stato riavviato dopo modifiche a gruppi o override;
- la voce boot AI tuning è attiva, se serve memoria GTT ampia per modelli grandi.

## 9. Aggiornamento e manutenzione

Ollama segue i pacchetti Arch.

```sh
sudo pacman -Syu
```

L'override systemd resta sotto `/etc/systemd/system/ollama.service.d/override.conf` e non viene sovrascritto dagli aggiornamenti del pacchetto.

La directory `/srv/models/ollama` può crescere rapidamente. Controlla lo spazio disponibile sul subvolume modelli.

```sh
btrfs filesystem usage /srv/models
ollama list
```
