<!--
Translator's certificate for one translated document. 8 C.F.R. 103.2(b)(3) (eCFR, current as of
2026-10-28, checked 2026-10-29): a foreign-language document "shall be accompanied by a full English
language translation which the translator has certified as complete and accurate, and by the
translator's certification that he or she is competent to translate from the foreign language into
English." This certificate states exactly those two things. Its signature, printed-name, date and contact
lines are the ones the I-751 instructions (ed. 04/01/24, checked 2026-10-29) say the certification must
include: the translator's signature, printed name, signature date and contact information.

How to use it: copy this file to the docs review's working folder as "translation certificate - <document>.md",
fill in the language, the document and its page count where you know them (leave the translator's
lines blank), and render it. When translations.py gives only the script ("a language written in Cyrillic
script"), leave the language line blank too: the translator names the language they certify.

  uv run --script "<plugin root>/scripts/packet/render_document.py" "<copy>.md" --formats pdf,docx

The translator translates the whole document (every page, stamps and handwriting included), fills
in and signs the certificate, and returns both. The packet places the original, then the full
English translation, then this certificate, under the same exhibit.
These comment lines are not rendered.
-->
# Certificate of Translation

I, ____________________________________ (translator's full name), certify that I am competent to translate from ______________________ (language) into English, and that the attached English translation of ______________________________________________ (document), ______ page(s), is complete and accurate.

Signature: ________________________________________

Printed name: _____________________________________

Address: _________________________________________

Telephone or email: ________________________________

Date: ____________________
