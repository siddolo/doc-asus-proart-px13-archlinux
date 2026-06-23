# Dwarf Star 4

DwarfStar è un motore di inferenza nativo ottimizzato innanzitutto per DeepSeek V4 Flash, con supporto per DeepSeek V4 PRO su macchine dotate di memoria molto elevata.

La configurazione kernel ottimizzata per workload AI è documentata in [Kernel AI tuning](kernel-ai-tuning.md).

### 1. Compilazione

Clonare il repository di ds4.

```sh
git clone https://github.com/antirez/ds4.git
cd ds4
```

Su Arch `rocm-hip-sdk` installa `hipcc, rocminfo, hipblas, hipblaslt, rocblas, hipcub` sotto `/opt/rocm`.
Il pacchetto `rocwmma` include già `rocwmma/internal/`; non servono i symlink `/opt/rocm` usati per Ubuntu documentati nel [repository ds4](https://github.com/antirez/ds4/blob/main/STRIXHALO.md).

```sh
sudo pacman -Syu
sudo pacman -S --needed \
  base-devel \
  rocm-hip-sdk rocwmma rocm-smi-lib
```

L'utente deve poter accedere a `/dev/kfd`.

```sh
sudo usermod -aG render "$USER"
```

Compilare ds4.

```sh
make strix-halo -j"$(nproc)"
```

### 2. Scaricare il modello

Scaricare il modello in `/srv/models/ds4`.
Il motivo di questa directory è nella guida di installazione: [Installazione base Arch Linux](installazione.md) crea un subvolume Btrfs dedicato `@models` e lo monta in `/srv/models`. Quel subvolume nasce per i modelli LLM, che possono occupare decine di GiB e hanno caratteristiche diverse da root e home. Tenerli sotto `/srv/models` evita di gonfiare il subvolume root, rende più chiaro cosa escludere o trattare diversamente in snapshot/backup e centralizza lo storage dei modelli anche per altri motori AI.

```sh
sudo mkdir /srv/models/ds4
sudo chown $USER:$USER /srv/models/ds4

wget https://huggingface.co/antirez/deepseek-v4-gguf/resolve/main/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf -O /srv/models/ds4/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf
```

### 3. Avviare DS4

Avvio ds4.

```sh
./ds4 -m /srv/models/ds4/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf
```

### 4. Performance

```
ds4> che modello sei?
processing 8 input tokens: 8/8 (100.0%)
Sono DeepSeek, l'ultimo modello creato da DeepSeek (non una versione precedente come R1). Sono un assistente puramente testuale, con una finestra di contesto di 1 milione di token e capacità di lettura di file (testo, immagini, PDF, Word, ecc.). Posso anche fornire link alla ricerca se attivi la funzione apposita. Come posso aiutarti?
ds4: prefill: 24.03 t/s, generation: 15.44 t/s
```
