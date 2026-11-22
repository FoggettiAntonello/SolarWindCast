# Verifica delle licenze Timestral — 22 novembre 2026

Consultati repository e model card ufficiali; scaricati soltanto i due testi
LICENSE, senza pesi o codice dei modelli. Le copie online alle revisioni usate
coincidono byte per byte, tramite SHA-256, con i testi già conservati qui:

| Modello | Revisione dei pesi | Testo applicabile |
| --- | --- | --- |
| 5M | `bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f` | [LICENSE](Timestral-5M_bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f_LICENSE.txt) |
| 28M | `49b26409ac87b5935539a5d8ffe7f397b720db47` | [LICENSE](Timestral-28M_49b26409ac87b5935539a5d8ffe7f397b720db47_LICENSE.txt) |

I pesi usano una **Modified MIT**. La clausola economica esclude i diritti
quando il fatturato mensile globale consolidato della società o del datore
di lavoro supera **20 milioni di dollari nel mese precedente**. Il testo
disciplina anche derivati, modifiche e lavori combinati; per tali utilizzi
va letto integralmente. Questa soglia non è una soglia di fatturato annuale.

Il codice Timestral usa invece **Apache-2.0**. La licenza del codice
SolarWindCast non sostituisce né modifica quella dei pesi. La v1 non li
redistribuisce e non li carica sul sito Azure.

Fonti delle revisioni effettivamente verificate:

- [Codice e Apache-2.0](https://raw.githubusercontent.com/mistralai/timestral/a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff/LICENSE).
- [5M LICENSE](https://huggingface.co/mistralai/Timestral-5M/raw/bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f/LICENSE).
- [28M LICENSE](https://huggingface.co/mistralai/Timestral-28M/raw/49b26409ac87b5935539a5d8ffe7f397b720db47/LICENSE).

Versione del codice usato: Timestral 1.0.0, commit fissato nel progetto.
I benchmark dichiarati da Mistral non sono risultati verificati su SolarWindCast.
