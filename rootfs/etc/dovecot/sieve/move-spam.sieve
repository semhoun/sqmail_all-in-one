/* Moves spam into Junk */
require ["fileinto"];
if anyof (header :contains "X-Spam-Flag" "YES"
    /* testing */
    /* ,header :contains "X-Spam-Status" "No" */
   )
{
  fileinto "Junk";
}
/* Other messages get filed into INBOX */
