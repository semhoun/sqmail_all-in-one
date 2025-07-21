require ["fileinto", "body"];
# rule:[Move to junk folder]
if anyof (header :contains "X-Spam-Flag" "YES")
{
  fileinto "Junk";
}
# rule:[Block spoofing messages]
if allof (body :text :contains "550 See http://spf.pobox.com/")
{
  discard;
}

