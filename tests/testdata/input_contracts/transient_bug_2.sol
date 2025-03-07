pragma solidity 0.8.25;
contract Generosity {
    mapping(address => bool) sentGifts;

    modifier nonreentrant {
        uint x;
        assembly {
            x := tload(0)
        }
        assert (x == 0);
        assembly {
            if tload(0) { revert(0, 0) }
            tstore(0, 1)
        }
        _;
        // Unlocks the guard, making the pattern composable.
        // After the function exits, it can be called again, even in the same transaction.
        assembly {
            x := tload(0)
        }
        assert (x == 1);

        assembly {
            tstore(0, 0)
        }
        assembly {
            x := tload(0)
        }
        assert (x == 1);
    }
    function claimGift() nonreentrant public {
        require(address(this).balance >= 1 ether);
        require(!sentGifts[msg.sender]);
        (bool success, ) = msg.sender.call{value: 1 ether}("");
        require(success);

        // In a reentrant function, doing this last would open up the vulnerability
        sentGifts[msg.sender] = true;
    }
}
