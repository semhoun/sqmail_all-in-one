require ["fileinto"];
if anyof (header :contains "X-Spam-Flag" "YES")
{
 fileinto "Spam";
}
/* Other messages get filed into INBOX */
