<?php
// Keep logout CSRF handling and secure session parameters in one place.
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Location: /', true, 303);
    exit;
}
$_POST['action'] = 'logout';
require __DIR__ . '/login.php';
