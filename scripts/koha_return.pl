#!/usr/bin/perl
use strict;
use warnings;
# koha_return.pl - Return (checkin) an item through Koha's internal circulation.
#
# The Koha REST API in this build has no checkin endpoint, so returns are done
# through the internal circulation module (C4::Circulation::AddReturn).
#
# Configuration:
#   KOHA_INSTANCE  Koha instance name      (default: library)
#   KOHA_CONF      Path to koha-conf.xml   (default: /etc/koha/sites/<instance>/koha-conf.xml)
#   KOHA_PERL5LIB  Perl module search path (default: /usr/share/koha/lib)
#
# Usage:
#   koha_return.pl BARCODE [BRANCHCODE] [INSTANCE]
#
# Returns a JSON document describing the result.

BEGIN {
    my $instance = $ARGV[2] || $ENV{KOHA_INSTANCE} || 'library';
    $ENV{KOHA_CONF} ||= "/etc/koha/sites/$instance/koha-conf.xml";
    my $perl5lib = $ENV{KOHA_PERL5LIB} || '/usr/share/koha/lib';
    push @INC, $perl5lib unless grep { $_ eq $perl5lib } @INC;
}

use Modern::Perl;
use C4::Circulation qw( AddReturn );
use C4::Context;
use JSON::PP;

my $barcode = shift or die "Usage: koha_return.pl BARCODE [BRANCHCODE] [INSTANCE]\n";
my $branch  = shift || 'GVP';

my $result = { barcode => $barcode };

my $item = Koha::Items->find( { barcode => $barcode } );
if ( !$item ) {
    $result->{ok}    = 0;
    $result->{error} = "Item with barcode '$barcode' not found";
    print JSON::PP->new->canonical->encode($result);
    exit 1;
}
$result->{item_id}   = $item->itemnumber;
$result->{biblio_id} = $item->biblionumber;

if ( !C4::Context->preference('UseCirculationDesks') ) {
    C4::Context->set_userenv( '0', '0', 'koha-mcp', 'koha-mcp', '', $branch, '' );
}

my ( $doreturn, $messages, $issue, $patron ) = C4::Circulation::AddReturn( $barcode, $branch );

$result->{returned} = $messages && $messages->{WasReturned} ? 1 : 0;
$result->{ok}       = 1;

if ( $messages && ref $messages eq 'HASH' ) {
    my $msg = {};
    for my $key ( keys %$messages ) {
        my $val = $messages->{$key};
        if ( $key eq 'BadBarcode' ) {
            $result->{error} = "Bad barcode: $barcode";
        }
        elsif ( ref $val eq 'HASH' || ref $val eq 'ARRAY' ) {
            $msg->{$key} = $val;
        }
        else {
            $msg->{$key} = $val;
        }
    }
    $result->{messages} = $msg if %$msg;
}

if ( $issue ) {
    $result->{patron_id}   = $issue->borrowernumber;
    $result->{checkout_id} = $issue->issue_id;
}
if ( $patron && ref $patron eq 'HASH' ) {
    $result->{patron_id} ||= $patron->{borrowernumber};
}

if ( $result->{error} ) {
    $result->{ok} = 0;
    print JSON::PP->new->canonical->encode($result);
    exit 1;
}

print JSON::PP->new->canonical->encode($result);
exit 0;
