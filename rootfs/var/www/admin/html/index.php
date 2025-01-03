<!DOCTYPE html>
<html lang="en" >

<head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252">
    
    <title>QMail AIO - Admin</title>

    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="/css/style.css">
    <link rel="stylesheet" href="/css/bootstrap.min.css">
    <link rel="stylesheet" href="/css/line-awesome.min.css">
</head>

<body>
    <div class="container">
    <div class="col-xs-12">
            <div class="text-center" style="padding-top: 30px; padding-bottom: 30px;">
                <img class="backdrop linktree">
                <h2 style="color: #ffffff; padding-top: 20px;">QMail AIO The Admin</h2>
            </div>
    </div>
    </div>

    <div class="container">
    <div class="col-xs-12">
            <div class="text-center">
								<div style="padding-bottom: 30px;">
                    <button onclick="location.href='/cgi/qmail-queue.php'" type="button" class="btn btn-outline-light shake" style="width: 80%; padding-top:10px; padding-bottom:10px; font-weight: 800;">QMail Queue</button>
                </div>
                <div style="padding-bottom: 30px;">
                    <button onclick="location.href='/cgi/vqadmin/vqadmin.cgi'" type="button" class="btn btn-outline-light " style="width: 80%; padding-top:10px; padding-bottom:10px; font-weight: 600;">VQAdmin</button>
                </div>
                <div style="padding-bottom: 30px;">
                    <button onclick="location.href='/cgi/qmailadmin'" type="button" class="btn btn-outline-light" style="width: 80%; padding-top:10px; padding-bottom:10px; font-weight: 600;">QMail Admin</button>
                </div>
<?php if (file_exists('/var/qmail/control/aio-conf/dmarc.conf')) { ?>
                <div style="padding-bottom: 30px;">
                    <button onclick="location.href='/dmarc/'" type="button" class="btn btn-outline-light" style="width: 80%; padding-top:10px; padding-bottom:10px; font-weight: 600;">DMARC</button>
                </div>
<?php } ?>
                <div style="padding-bottom: 30px;">
                    <button onclick="location.href='/info.php'" type="button" class="btn btn-outline-light" style="width: 80%; padding-top:10px; padding-bottom:10px; font-weight: 600;">Info</button>
                </div>
            </div>
    </div>
    </div>

		<div class="text-center">
				<a href="https://github.com/semhoun/qmail_all-in-one" style="color: #34312f;">powered by QMail All-In-One</a>
		</div>


    <script src="/js/jquery-3.6.0.slim.min.js"></script>
    <script src="/js/bootstrap.bundle.min.js"></script>
</body>

</html>