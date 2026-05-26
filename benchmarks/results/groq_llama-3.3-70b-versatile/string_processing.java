public class StringProcessing {
    public static int countVowels(String str) {
        int count = 0;
        for (char c : str.toLowerCase().toCharArray()) {
            if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u') {
                count++;
            }
        }
        return count;
    }

    public static void reverseString(char[] str) {
        int len = str.length;
        for (int i = 0; i < len / 2; i++) {
            char temp = str[i];
            str[i] = str[len - 1 - i];
            str[len - 1 - i] = temp;
        }
    }

    public static int isPalindrome(String str) {
        int len = str.length();
        for (int i = 0; i < len / 2; i++) {
            if (Character.toLowerCase(str.charAt(i)) != Character.toLowerCase(str.charAt(len - 1 - i))) {
                return 0;
            }
        }
        return 1;
    }

    public static void toUpperCase(char[] str) {
        for (int i = 0; i < str.length; i++) {
            str[i] = Character.toUpperCase(str[i]);
        }
    }

    public static void main(String[] args) {
        char[] text = "Hello World".toCharArray();
        System.out.println("Vowels: " + countVowels(new String(text)));

        char[] palindrome = "racecar".toCharArray();
        if (isPalindrome(new String(palindrome))) {
            System.out.println("'" + new String(palindrome) + "' is a palindrome");
        }

        reverseString(text);
        System.out.println("Reversed: " + new String(text));

        toUpperCase(text);
        System.out.println("Upper: " + new String(text));
    }
}