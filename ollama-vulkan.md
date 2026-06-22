# Ollama Vulkan su ASUS ProArt PX13

Questa guida descrive come installare e provare il backend Vulkan di Ollama su Arch Linux per AMD Ryzen AI Max+ 395 / Radeon 8060S, mantenendo gli stessi modelli in `/srv/models/ollama`. Il backend ROCm è documentato separatamente in [Ollama ROCm](ollama-rocm.md) e su questo PC al momento è più performante.

La configurazione kernel ottimizzata per workload AI è documentata in [Kernel AI tuning](kernel-ai-tuning.md). Il tuning GTT/TTM è utile anche con Vulkan, perché la Radeon 8060S usa memoria condivisa e il backend Vulkan la espone come memoria disponibile alla GPU.

## 1. Scelta del backend

Ollama 0.30.10 supporta la variabile `OLLAMA_VULKAN`, ma il suo ruolo è abilitare o disabilitare la discovery del backend Vulkan. Non forza Vulkan se è disponibile anche ROCm.

Su Linux, con `ollama-rocm` e `ollama-vulkan` installati insieme, Ollama rileva la stessa Radeon 8060S sia tramite ROCm sia tramite Vulkan e preferisce ROCm. Per attivare esplicitamente Vulkan servono queste variabili:

- `OLLAMA_VULKAN=1`: abilita esplicitamente la discovery Vulkan;
- `OLLAMA_LLM_LIBRARY=vulkan`: limita la discovery alla directory backend `/usr/lib/ollama/vulkan`;
- `OLLAMA_IGPU_ENABLE=1`: permette a Ollama di usare la Radeon 8060S quando il backend Vulkan la classifica come iGPU.

Senza `OLLAMA_IGPU_ENABLE=1`, i log mostrano la GPU Vulkan ma poi la scartano con un messaggio simile a `dropping integrated GPU; to enable, set OLLAMA_IGPU_ENABLE=1`.

La selezione del backend viene gestita con un solo drop-in systemd attivo alla volta. Systemd carica tutti i file `*.conf` presenti in `/etc/systemd/system/ollama.service.d/`; per questo `backend-vulkan.conf` e `backend-rocm.conf` non devono essere attivi insieme. La convenzione usata qui è: il backend attivo ha estensione `.conf`, il backend inattivo resta presente con estensione `.conf.disabled`.

## 2. Installazione

Installa il backend Vulkan e gli strumenti di verifica Vulkan.

```sh
sudo pacman -Syu --needed --noconfirm ollama-vulkan vulkan-radeon vulkan-tools
```

Verifica i pacchetti rilevanti.

```sh
pacman -Q ollama ollama-rocm ollama-vulkan vulkan-radeon vulkan-tools vulkan-icd-loader
```

Su questo sistema sono stati verificati:

```text
ollama 0.30.10-1
ollama-rocm 0.30.10-1
ollama-vulkan 0.30.10-1
vulkan-radeon 1:26.1.3-2
vulkan-tools 1.4.350.1-1
vulkan-icd-loader 1.4.350.1-1
```

## 3. Verifiche Vulkan

Verifica che la Radeon 8060S sia visibile a Vulkan.

```sh
vulkaninfo --summary
```

L'output deve includere una GPU AMD simile a:

```text
AMD Radeon 8060S Graphics (RADV STRIX_HALO)
```

Verifica che il backend Vulkan di Ollama sia installato.

```sh
stat /usr/lib/ollama/vulkan/libggml-vulkan.so
```

Verifica che Ollama conosca le variabili di selezione backend.

```sh
ollama serve --help
```

In Ollama 0.30.10 `OLLAMA_LLM_LIBRARY` compare nell'help come variabile per bypassare l'autodetection. `OLLAMA_VULKAN` è supportata dal binario e dalla configurazione upstream, ma può non comparire nell'help sintetico del comando `serve`.

## 4. Drop-in systemd

Il servizio standard `ollama.service` usa la porta locale `11434`. Per attivare Vulkan, mantieni il drop-in dei modelli e abilita solo il drop-in Vulkan.

```sh
sudo install -d -m 0755 /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_MODELS=/srv/models/ollama"
EOF
sudo chmod 0644 /etc/systemd/system/ollama.service.d/override.conf
```

Disabilita l'eventuale backend ROCm attivo.

```sh
if [ -f /etc/systemd/system/ollama.service.d/backend-rocm.conf ]; then
  sudo mv /etc/systemd/system/ollama.service.d/backend-rocm.conf \
    /etc/systemd/system/ollama.service.d/backend-rocm.conf.disabled
fi
```

Riattiva il drop-in Vulkan se esiste già come file disabilitato.

```sh
if [ -f /etc/systemd/system/ollama.service.d/backend-vulkan.conf.disabled ]; then
  sudo mv /etc/systemd/system/ollama.service.d/backend-vulkan.conf.disabled \
    /etc/systemd/system/ollama.service.d/backend-vulkan.conf
fi
```

Se il drop-in Vulkan non esiste ancora, crealo una sola volta.

```sh
if [ ! -f /etc/systemd/system/ollama.service.d/backend-vulkan.conf ]; then
  sudo tee /etc/systemd/system/ollama.service.d/backend-vulkan.conf >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_VULKAN=1"
Environment="OLLAMA_LLM_LIBRARY=vulkan"
Environment="OLLAMA_IGPU_ENABLE=1"
EOF
  sudo chmod 0644 /etc/systemd/system/ollama.service.d/backend-vulkan.conf
fi
```

Ricarica systemd e riavvia il servizio.

```sh
sudo systemctl daemon-reload
sudo systemctl restart ollama.service
```

## 5. Verifiche

Verifica l'environment effettivo.

```sh
systemctl show -p Environment ollama.service
```

L'output deve includere:

```text
OLLAMA_MODELS=/srv/models/ollama
OLLAMA_VULKAN=1
OLLAMA_LLM_LIBRARY=vulkan
OLLAMA_IGPU_ENABLE=1
```

Verifica che sia attivo un solo drop-in backend.

```sh
ls /etc/systemd/system/ollama.service.d/backend-*.conf
```

Con Vulkan attivo deve comparire solo:

```text
/etc/systemd/system/ollama.service.d/backend-vulkan.conf
```

Verifica nei log che il backend usato sia Vulkan.

```sh
sudo journalctl -u ollama.service -b --no-pager | grep -E 'library=Vulkan|RADV_STRIX_HALO|RADV STRIX_HALO|OLLAMA_LLM_LIBRARY:vulkan'
```

Su questo PX13 il log verificato è:

```text
inference compute ... library=Vulkan ... description="AMD Radeon 8060S Graphics (RADV STRIX_HALO)" ... type=iGPU total="124.0 GiB"
```

## 6. Misura performance

Usa lo stesso modello, lo stesso prompt e le stesse opzioni usate nella guida ROCm. Per i modelli reasoning/thinking usa `--think=false`, così il benchmark misura la risposta richiesta e non anche il ragionamento interno.

Esempio con il servizio standard sulla porta `11434`:

```sh
ollama run --think=false --verbose qwen3.6:27b \
  "Scrivi una spiegazione breve di cosa fa systemd-boot su Arch Linux."
```

Risultato Vulkan misurato su questo sistema con `qwen3.6:27b`:

```text
ollama run --think=false --verbose qwen3.6:27b "Scrivi una spiegazione breve di cosa fa systemd-boot su Arch Linux."
**systemd-boot** è un bootloader semplice e leggero utilizzato principalmente in ambienti basati su UEFI (come Arch Linux). A differenza di bootloader più complessi come GRUB, non include funzionalità 
avanzate come la gestione automatica dei menu o il caricamento di moduli del kernel tramite file di configurazione personalizzati.

Funziona leggendo direttamente i file EFI dal percorso `/boot/loader/entries/` e mostra un semplice menu al avvio con le opzioni definite dall'utente. È particolarmente apprezzato per la sua 
semplicità, velocità e bassa complessità, rendendolo ideale per sistemi dove non sono necessarie funzionalità avanzate di bootloader.

In Arch Linux, `systemd-boot` viene spesso configurato manualmente tramite il comando `bootctl`, che semplifica l'installazione e la gestione delle opzioni di avvio.

total duration:       20.607304374s
load duration:        6.628058944s
prompt eval count:    27 token(s)
prompt eval duration: 915.745ms
prompt eval rate:     29.48 tokens/s
eval count:           169 token(s)
eval duration:        13.061187s
eval rate:            12.94 tokens/s

```

Confronto con la run ROCm documentata in [Ollama ROCm](ollama-rocm.md#7-misura-performance):

| Backend | Modello       | Prompt eval rate |     Eval rate | Note                         |
| ------- | ------------- | ---------------: | ------------: | ---------------------------- |
| ROCm    | `qwen3.6:27b` |   301.98 token/s | 12.76 token/s | `backend-rocm.conf` attivo   |
| Vulkan  | `qwen3.6:27b` |    29.48 token/s | 12.94 token/s | `backend-vulkan.conf` attivo |

Il confronto mostra una differenza importante: in questa run ROCm è molto più veloce nel prompt processing, mentre la token generation Vulkan è simile o leggermente più alta.

## 7. Passare a ROCm

Per passare a ROCm, rinomina i drop-in in modo che sia attivo solo `backend-rocm.conf`.

```sh
if [ -f /etc/systemd/system/ollama.service.d/backend-vulkan.conf ]; then
  sudo mv /etc/systemd/system/ollama.service.d/backend-vulkan.conf \
    /etc/systemd/system/ollama.service.d/backend-vulkan.conf.disabled
fi
if [ -f /etc/systemd/system/ollama.service.d/backend-rocm.conf.disabled ]; then
  sudo mv /etc/systemd/system/ollama.service.d/backend-rocm.conf.disabled \
    /etc/systemd/system/ollama.service.d/backend-rocm.conf
fi
sudo systemctl daemon-reload
sudo systemctl restart ollama.service
```

Verifica che il servizio usi ROCm.

```sh
systemctl show -p Environment ollama.service
```

L'output deve mantenere `OLLAMA_MODELS=/srv/models/ollama`, includere `OLLAMA_LLM_LIBRARY=rocm_v7_2` e non includere più `OLLAMA_LLM_LIBRARY=vulkan`.

## 8. Diagnostica

Se Vulkan non viene usato, controlla nell'ordine:

- `ollama-vulkan` installato;
- `/usr/lib/ollama/vulkan/libggml-vulkan.so` presente;
- `vulkaninfo --summary` mostra `AMD Radeon 8060S Graphics (RADV STRIX_HALO)`;
- `/etc/systemd/system/ollama.service.d/backend-vulkan.conf` è l'unico drop-in backend attivo;
- `OLLAMA_LLM_LIBRARY=vulkan` impostato nel servizio;
- `OLLAMA_IGPU_ENABLE=1` impostato, perché Vulkan classifica la Radeon 8060S come iGPU;
- `journalctl` mostra `library=Vulkan`.

Per selezionare esplicitamente un device Vulkan, usa `GGML_VK_VISIBLE_DEVICES`, per esempio `GGML_VK_VISIBLE_DEVICES=0`. Su questo portatile normalmente c'è una sola GPU Vulkan rilevante, quindi non serve impostarlo manualmente.
