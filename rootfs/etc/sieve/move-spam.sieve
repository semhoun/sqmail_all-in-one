require ["fileinto"];
if anyof (header :contains "X-Spam-Flag" "YES")
{
 fileinto "Junk";
}
/* Other messages get filed into INBOX */
