from harness.canon.glossary import Glossary


def test_glossary_replaces_latin_and_wrong_spellings():
    g = Glossary.load()
    assert g.apply("Velerad told Geralt that Foltest's sister Adda died in Vizim.") == \
        "Велерад told Ґеральт that Фольтеста sister Адда died in Визім."
    assert g.apply("Veleral and Segelen met Ostrit at the Lynvar Gate") == \
        "Велерад and Сеґелін met Остріт at the брама Линварів"
    assert g.apply("Ґеральт мовчав") == "Ґеральт мовчав"          # canonical text is untouched
    assert g.apply("Geralt of Rivia") == "Ґеральт"                  # the longest variant wins
