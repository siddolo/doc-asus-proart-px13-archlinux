# Repository Guidelines

Questo repository è una base documentale per ASUS ProArt PX13 HN7306EAC con Arch Linux. La cartella è anche un vault Obsidian.

I documenti Markdown non sono semplici log cronologici di quello che viene fatto: devono essere mantenuti come guide leggibili, ripetibili e utili anche in futuro. Quando aggiungi o modifichi contenuti, descrivi il contesto, la procedura, le verifiche e le motivazioni tecniche rilevanti.

## Struttura

- `README.md`: indice del vault/repository.
- `installazione-base-arch-linux.md`: guida principale per installazione base e configurazione iniziale del portatile.
- I documenti guida pubblicabili possono stare in root o in sottocartelle tematiche, per esempio `ollama/installazione.md` e `ollama/tuning.md`.
- `configs/`: file installabili citati dalle guide, organizzati per area tecnica.
- `exports/`: output generati per pubblicazione, in particolare MediaWiki; rispecchia i path dei documenti Markdown, per esempio `ollama/installazione.md` diventa `exports/ollama/installazione.wiki`.
- `tools/`: script di supporto per generare o verificare gli export.
- `Makefile`: comandi per generare e verificare gli export MediaWiki dai documenti Markdown pubblicabili.
- `.obsidian/`: configurazione del vault Obsidian.
- `to-do/`: appunti temporanei locali, esclusi dal repository; può rispecchiare le stesse aree tematiche dei documenti, per esempio `to-do/ollama/`.

## Convenzioni

- Il Markdown è la sorgente autorevole; gli export in `exports/` vanno rigenerati con `make wiki` o verificati con `make check`.
- `README.md` è solo l'indice dei documenti guida; non deve elencare script, configurazioni installabili, export generati o appunti locali.
- I documenti Markdown pubblicabili sono tutti gli `.md` fuori da `.obsidian/`, `configs/`, `exports/`, `tools/` e `to-do/`, escluso `AGENTS.md`.
- Usa link Markdown relativi, per esempio `[Installazione base](installazione-base-arch-linux.md)`, invece dei wikilink Obsidian, così i link restano compatibili sia con Obsidian sia con GitHub.
- Mantieni i file installabili separati dalla documentazione e citati dalle guide quando servono; per un'area tematica usa `configs/<area>/`.
- Per evoluzioni autonome piccole crea un nuovo documento Markdown in root, per esempio `ollama.md`; se l'argomento cresce, usa una sottocartella tematica, per esempio `ollama/installazione.md`.
- Aggiorna `README.md` quando aggiungi documenti principali.
