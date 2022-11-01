require ["body"];
if allof (body :text :contains "550 See http://spf.pobox.com/")
{
        discard;
}

