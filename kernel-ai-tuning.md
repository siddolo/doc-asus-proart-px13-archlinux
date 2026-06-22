# Kernel AI tuning su ASUS ProArt PX13

Questa guida descrive il tuning kernel usato per workload AI generici su AMD Ryzen AI Max+ 395 / Radeon 8060S, sul portatile PX13 HN7306EA. L'obiettivo è aumentare la memoria unificata indirizzabile dalla GPU per inferenza LLM e workload ROCm/Vulkan, mantenendo una voce boot non modificata come fallback.

## 1. Contesto hardware

Il Ryzen AI Max+ 395 è una APU Strix Halo con CPU Zen 5, GPU RDNA 3.5 e memoria fisicamente condivisa. Su Linux/ROCm il target GPU è `gfx1151`.

Su questo tipo di sistema la memoria video non va pensata come una VRAM discreta separata: la GPU può mappare memoria di sistema tramite GPUVM/GTT. La documentazione AMD per RDNA3.5 consiglia di evitare grandi riserve statiche nel firmware quando lo scopo è usare workload AI, perché la memoria riservata alla GPU non è disponibile alla CPU anche quando la GPU non la sta usando.

La scelta è quindi:

- mantenere una riserva firmware/BIOS contenuta quando il firmware lo permette (su questa versione di BIOS non è possibile modificare tale parametro);
- aumentare il limite GTT/TTM lato kernel;
- usare una voce boot dedicata al tuning AI;
- mantenere la voce `Arch Linux` originale come fallback.

## 2. Stato pre-tuning

Verifica i parametri effettivi del boot corrente.

```sh
cat /proc/cmdline
```

Su questo sistema prima del tuning non erano presenti parametri specifici per IOMMU, GTT o TTM.

Controlla la memoria totale vista dal kernel.

```sh
grep '^MemTotal:' /proc/meminfo
```

Su questa macchina il valore era circa `127396268 kB`, cioè circa 121.5 GiB realmente disponibili a Linux.

Controlla i limiti GPU correnti.

```sh
sudo cat /sys/module/amdgpu/parameters/gttsize
cat /sys/module/ttm/parameters/pages_limit
```

Prima del tuning `amdgpu.gttsize` era in automatico (`-1`) e `ttm.pages_limit` era circa metà della RAM.

Controlla la memoria GPU esposta dal driver.

```sh
sudo sh -c 'for f in /sys/class/drm/card*/device/mem_info_*; do
  [ -e "$f" ] || continue
  printf "%s=" "$f"
  cat "$f"
done'
```

Prima del tuning il driver esponeva circa 4 GiB di VRAM visibile/firmware-reserved e circa 60.75 GiB di GTT.

## 3. Parametri per il tuning

La nuova voce del boot-menu `Arch Linux AI tuning` userà questi parametri aggiuntivi:

```text
amd_iommu=off amdgpu.gttsize=122880 ttm.pages_limit=31457280
```

`amd_iommu=off` disabilita l'AMD IOMMU. Su benchmark Strix Halo pubblicati nella [issue kyuz0/amd-strix-halo-toolboxes#66](https://github.com/kyuz0/amd-strix-halo-toolboxes/issues/66#issuecomment-4460612951), questa scelta ha mostrato un vantaggio del 5-12% rispetto a IOMMU attivo o `iommu=pt` in workload llama.cpp/ROCm, soprattutto in prompt processing e batch paralleli.

Il trade-off è importante: disabilitare IOMMU riduce l'isolamento DMA. È una scelta orientata alle prestazioni per inferenza locale; non è ideale se servono VFIO/passthrough, isolamento DMA stretto o una postura di sicurezza più conservativa, soprattutto su un laptop con porte USB4.

`amdgpu.gttsize=122880` imposta a 120 GiB il limite GTT utente del driver AMDGPU. Il valore è in MiB.

`ttm.pages_limit=31457280` imposta il limite TTM a 31.457.280 pagine da 4 KiB, cioè 120 GiB. Il valore è stato scelto perché la RAM totale esposta a Linux è circa 121.5 GiB: resta più prudente dei valori da 124 GiB spesso citati per sistemi dove la riserva firmware è più piccola.

Su questo BIOS ASUS non è stata trovata una voce per modificare la memoria grafica statica/UMA; la riserva firmware osservata resta quindi circa 4 GiB. Per questo 120 GiB è una scelta più coerente con la memoria realmente disponibile rispetto ai valori da 124 GiB usati su sistemi dove la riserva firmware è più piccola. Se un aggiornamento BIOS futuro espone una voce per ridurre la riserva a 512 MiB, si può rivalutare un limite più alto.

## 4. Creazione della voce systemd-boot

Crea una nuova entry per il kernel `linux` con tuning AI.

```sh
sudo tee /boot/loader/entries/arch-ai-tuning.conf >/dev/null <<'EOF'
title Arch Linux AI tuning
linux /vmlinuz-linux
initrd /amd-ucode.img
initrd /initramfs-linux.img
options cryptdevice=UUID=d294d825-c130-4bf4-884f-be2bbb7b9ea2:cryptroot:allow-discards root=/dev/mapper/vg0-root rootflags=subvol=@ resume=UUID=dac24720-c492-4442-9bcf-7039eb94c386 rw amd_iommu=off amdgpu.gttsize=122880 ttm.pages_limit=31457280
EOF
```

Rendi la nuova entry il default di `systemd-boot`, mantenendo timeout e console mode invariati.

```sh
sudo tee /boot/loader/loader.conf >/dev/null <<'EOF'
default arch-ai-tuning.conf
timeout 5
console-mode max
editor yes
EOF
```

La voce precedente `Arch Linux` resta in `/boot/loader/entries/arch.conf` senza tuning e continua a essere disponibile dal menu boot. Anche `Arch Linux LTS` resta disponibile come fallback kernel LTS.

## 5. Verifiche prima del reboot

Controlla il menu boot visto da `systemd-boot`.

```sh
bootctl list
```

L'output atteso deve includere:

```text
Arch Linux AI tuning (default)
Arch Linux
Arch Linux LTS
```

Durante la sessione corrente `bootctl list` può mostrare ancora `Arch Linux` come `selected`, perché è la voce usata per il boot già avvenuto. Dopo il reboot, la voce selezionata dovrà diventare `Arch Linux AI tuning`.

## 6. Verifiche dopo reboot

Dopo il reboot selezionato sulla nuova entry, verifica che la voce AI tuning sia effettivamente quella avviata.

```sh
bootctl list
```

Risultato verificato:

```text
Arch Linux AI tuning (default) (selected)
```

Verifica poi che i parametri siano effettivi.

```sh
cat /proc/cmdline
```

Devono comparire:

```text
amd_iommu=off amdgpu.gttsize=122880 ttm.pages_limit=31457280
```

Risultato verificato: i tre parametri compaiono nella riga kernel attiva.

Controllare IOMMU groups per GPU e NPU:

```sh
test -e /sys/bus/pci/devices/0000:c4:00.0/iommu_group && echo gpu_iommu_group=present || echo gpu_iommu_group=absent
test -e /sys/bus/pci/devices/0000:c5:00.1/iommu_group && echo npu_iommu_group=present || echo npu_iommu_group=absent
```

Risultato atteso:

```text
gpu_iommu_group=absent
npu_iommu_group=absent
```

Verifica i nuovi limiti GTT/TTM.

```sh
sudo cat /sys/module/amdgpu/parameters/gttsize
cat /sys/module/ttm/parameters/pages_limit
sudo sh -c 'for f in /sys/class/drm/card*/device/mem_info_gtt_total /sys/class/drm/card*/device/mem_info_vram_total /sys/class/drm/card*/device/mem_info_vis_vram_total; do
  [ -e "$f" ] || continue
  printf "%s=" "$f"
  cat "$f"
done'
```

L'output atteso dopo il reboot è:

```text
gttsize=122880
ttm.pages_limit=31457280
/sys/class/drm/card1/device/mem_info_gtt_total=128849018880
/sys/class/drm/card1/device/mem_info_vram_total=4294967296
/sys/class/drm/card1/device/mem_info_vis_vram_total=4294967296
```

`mem_info_gtt_total=128849018880` corrisponde a 120 GiB, quindi il limite GTT/TTM è applicato. La VRAM firmware-reserved resta 4 GiB, coerente con l'assenza di una voce BIOS visibile per ridurla.

Verifica che ROCm continui a vedere la GPU Strix Halo.

```sh
/opt/rocm/bin/rocm_agent_enumerator
/opt/rocm/bin/rocminfo | grep -Ei 'gfx1151|Marketing Name|AMD Radeon 8060S'
```

`rocm_agent_enumerator` deve includere `gfx1151`.

Risultato verificato:

```text
gfx1151
AMD Radeon 8060S Graphics
```

## 7. Ripristino rapido

Se il sistema mostra regressioni grafiche, errori DRM/IOMMU, instabilità GPU o problemi con periferiche, riavvia e scegli `Arch Linux` dal menu `systemd-boot`. Quella voce non contiene i parametri AI tuning.

Per annullare il default senza rimuovere la voce:

```sh
sudo sed -i 's/^default .*/default arch.conf/' /boot/loader/loader.conf
```

Per rimuovere completamente la voce tuned:

```sh
sudo rm /boot/loader/entries/arch-ai-tuning.conf
sudo sed -i 's/^default .*/default arch.conf/' /boot/loader/loader.conf
```

## 8. Note

Questo tuning è generale: può aiutare Ollama, llama.cpp, vLLM, PyTorch ROCm, ComfyUI e altri motori AI che usano la GPU integrata Strix Halo e memoria unificata ampia.

Su Strix Halo il backend migliore può cambiare tra ROCm e Vulkan in base a modello, quantizzazione, lunghezza contesto e rapporto tra prompt processing e token generation.

Se in futuro viene usata virtualizzazione con passthrough, VFIO o workload che richiedono IOMMU, considera una voce alternativa con IOMMU attivo (oppure usa il fallback `Arch Linux`).
