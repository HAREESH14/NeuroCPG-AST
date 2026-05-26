import java.util.Scanner;

public class CountVowelsAndConsonants {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        String s = scanner.next();
        int vowels = 0, consonants = 0;
        for (int i = 0; i < s.length(); ++i) {
            char c = Character.toLowerCase(s.charAt(i));
            if (c >= 'a' && c <= 'z') {
                if (c=='a' || c=='e' || c=='i' || c=='o' || c=='u') ++vowels;
                else ++consonants;
            }
        }
        System.out.println("Vowels: " + vowels + ", Consonants: " + consonants);
    }
}