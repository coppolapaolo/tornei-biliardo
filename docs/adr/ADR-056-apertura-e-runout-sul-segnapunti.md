

## Emendamento (2026-09-29, ADR-075, passo 4)

Chi apre e chi spacca non si **ereditano** più dal campionato: si **copiano**
sulla gara quando nasce (`GaraService._copia_dal_campionato`), come tutti gli
altri valori del campionato, e la migration `20260929_valori_del_campionato_copiati`
ha scritto sulle gare esistenti il valore che usavano. La voce «Eredita dal
campionato» sparisce dai moduli. Se il direttore cambia la regola del
campionato, l'app propone a quali gare non ancora avviate applicarla
(`models/campionato/proposte.py`).
