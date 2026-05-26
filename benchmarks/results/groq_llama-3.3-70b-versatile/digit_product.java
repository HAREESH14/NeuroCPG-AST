import java.util.Scanner;

public class DigitProduct {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        int prod = 1;
        while (n > 0) { 
            prod *= (n % 10); 
            n /= 10; 
        }
        System.out.println("Product of digits: " + prod);
    }
}