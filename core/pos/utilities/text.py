# Acrónimos que deben quedarse en mayúsculas al normalizar un nombre a estilo
# Capital (ej. "IESS SEGURO SOCIAL" -> "IESS Seguro Social", no "Iess Seguro
# Social"). Ampliar esta lista si aparece una institución nueva que lo
# necesite.
PRESERVE_ACRONYMS = {
    'IESS', 'SRI', 'RUC', 'GAD', 'IVA', 'BCE', 'MIES', 'MSP', 'ONG', 'ONU', 'INEC',
}


def smart_title_case(text):
    if not text:
        return text
    words = text.split(' ')
    result = []
    for word in words:
        # El acrónimo puede venir con puntuación pegada (ej. "IESS,"), se
        # compara solo el núcleo alfabético contra la lista.
        core = word.strip('.,()"\'-').upper()
        if core in PRESERVE_ACRONYMS:
            result.append(word.upper())
        else:
            result.append(word.title())
    return ' '.join(result)
