import java.util.Scanner;

public class SumOfDigits {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        if (n < 0) n = -n;
        int s = 0;
        while (n > 0) { 
            s += n % 10; 
            n /= 10; 
        }
        System.out.println("Sum of digits: " + s);
    }
}